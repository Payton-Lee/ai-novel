"""人物定义 Agent — 对话式主图.

图结构 (与 world_builder / outline_planner 同构, chat loop + 持久化):
    START → character_builder → (tools_condition) → tools → character_builder → ... → END

多轮对话依赖 thread_id, 由 LangGraph 平台自动持久化。
char_draft 每轮从 HumanMessage 现场组装, 注入系统提示词作为稳定记忆。
"""

from __future__ import annotations

import re
from typing import Optional

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from character_builder.prompts import CHARACTER_BUILDER_SYSTEM_PROMPT
from character_builder.render import _extract_mermaid_block
from character_builder.state import CharacterBuilderState
from character_builder.tools import (
    CHARACTER_BUILDER_TOOLS,
    generate_character_cards,
    generate_relationship_graph,
)
from novel.llm_factory import get_llm_from_config

_HTML_PATH_RE = re.compile(r"(output/character_relations/[\w-]+\.html)")


def _assemble_draft(messages: list[AnyMessage]) -> str:
    """从对话历史中组装人物设定草稿 (只取用户真实输入)."""
    parts: list[str] = []
    for m in messages:
        if m.type == "human":
            text = str(m.content).strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def character_builder_node(
    state: CharacterBuilderState, config: Optional[RunnableConfig] = None
) -> dict:
    """主对话节点: 结合人物设定记忆调用 LLM, 支持工具调用."""
    llm = get_llm_from_config(config)

    draft = _assemble_draft(state.get("messages", []))
    system = CHARACTER_BUILDER_SYSTEM_PROMPT

    # 注入已提供的背景素材
    context_bits = []
    if state.get("genre"):
        context_bits.append(f"题材: {state['genre']}")
    if state.get("premise"):
        context_bits.append(f"故事前提: {state['premise']}")
    if state.get("world_bible"):
        context_bits.append(f"世界观圣经:\n{state['world_bible']}")
    if state.get("outline_draft"):
        context_bits.append(f"大纲参考:\n{state['outline_draft']}")
    if context_bits:
        system += "\n\n## 作者已提供的背景素材\n" + "\n\n".join(context_bits)

    if draft:
        system += (
            "\n\n## 当前人物设定草稿 (作者对话中确认的内容, 供你保持一致性)\n"
            f"{draft}\n"
        )

    llm_with_tools = llm.bind_tools(CHARACTER_BUILDER_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )

    return {"messages": [ai_msg], "char_draft": draft}


def tools_node(
    state: CharacterBuilderState, config: Optional[RunnableConfig] = None
) -> dict:
    """工具执行节点; 同步人物卡片与关系图产物到状态."""
    node = ToolNode(CHARACTER_BUILDER_TOOLS)
    result = node.invoke(state)

    # 找到本轮所有 tool_call 结果, 同步关键产物
    tool_messages = {rm.tool_call_id: rm for rm in result.get("messages", []) if rm.type == "tool"}

    character_cards = None
    relationship_graph = None
    html_path = None

    for m in reversed(state.get("messages", [])):
        if m.type != "ai":
            continue
        for tc in getattr(m, "tool_calls", []) or []:
            tm = tool_messages.get(tc["id"])
            if not tm:
                continue
            content = str(tm.content)
            if tc["name"] == generate_character_cards.name:
                character_cards = content
            elif tc["name"] == generate_relationship_graph.name:
                mermaid = _extract_mermaid_block(content)
                if mermaid:
                    relationship_graph = mermaid
                path_m = _HTML_PATH_RE.search(content)
                if path_m:
                    html_path = path_m.group(1)

    if character_cards:
        result["character_cards"] = character_cards
    if relationship_graph:
        result["relationship_graph"] = relationship_graph
    if html_path:
        result["html_path"] = html_path
    return result


def _build_graph() -> StateGraph:
    """构建人物定义器 StateGraph."""
    builder = StateGraph(CharacterBuilderState)

    builder.add_node("character_builder", character_builder_node)
    builder.add_node("tools", tools_node)

    builder.add_edge(START, "character_builder")
    builder.add_conditional_edges(
        "character_builder",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "character_builder")

    return builder


# 编译图 — 无自定义 checkpointer (LangGraph 平台自动持久化, 依赖 thread_id)
graph = _build_graph().compile(name="character_builder")
