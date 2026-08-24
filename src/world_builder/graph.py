"""世界观编辑器 — 对话式 Agent 主图.

图结构 (chat loop + 持久化):
    START → world_builder → (tools_condition) → tools → world_builder → ... → END

多轮对话依赖 thread_id, 由 LangGraph 平台自动持久化。
world_draft 每轮从 HumanMessage 现场组装, 注入系统提示词作为稳定记忆。
"""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from novel.llm_factory import get_llm_from_config
from world_builder.prompts import WORLD_BUILDER_SYSTEM_PROMPT
from world_builder.state import WorldBuilderState
from world_builder.tools import WORLD_BUILDER_TOOLS, generate_world_bible


def _assemble_draft(messages: list[AnyMessage]) -> str:
    """从对话历史中组装已确认的设定摘要 (只取用户真实输入)."""
    parts: list[str] = []
    for m in messages:
        if m.type == "human":
            text = str(m.content).strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def world_builder_node(
    state: WorldBuilderState, config: Optional[RunnableConfig] = None
) -> dict:
    """主对话节点: 结合设定记忆调用 LLM, 支持工具调用."""
    llm = get_llm_from_config(config)

    # 组装设定摘要并注入系统提示词 (长对话中的稳定记忆)
    draft = _assemble_draft(state.get("messages", []))
    system = WORLD_BUILDER_SYSTEM_PROMPT
    if draft:
        system += (
            "\n\n## 当前已确认的设定摘要 (作者提供的原始描述, 供你保持一致性)\n"
            f"{draft}\n"
        )

    llm_with_tools = llm.bind_tools(WORLD_BUILDER_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )

    return {"messages": [ai_msg], "world_draft": draft}


def tools_node(state: WorldBuilderState, config: Optional[RunnableConfig] = None) -> dict:
    """工具执行节点; 若导出了世界圣经, 同步写入状态."""
    node = ToolNode(WORLD_BUILDER_TOOLS)
    result = node.invoke(state)

    # 检测 generate_world_bible 调用, 把产物同步到 world_bible 字段
    world_bible = None
    for m in reversed(state.get("messages", [])):
        if m.type != "ai":
            continue
        for tc in getattr(m, "tool_calls", []) or []:
            if tc["name"] == generate_world_bible.name:
                for rm in result.get("messages", []):
                    if rm.type == "tool" and rm.tool_call_id == tc["id"]:
                        world_bible = rm.content
                        break
        if world_bible:
            break

    if world_bible:
        result["world_bible"] = world_bible
    return result


def _build_graph() -> StateGraph:
    """构建世界观编辑器 StateGraph."""
    builder = StateGraph(WorldBuilderState)

    builder.add_node("world_builder", world_builder_node)
    builder.add_node("tools", tools_node)

    builder.add_edge(START, "world_builder")
    builder.add_conditional_edges(
        "world_builder",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "world_builder")

    return builder


# 编译图 — 无自定义 checkpointer (LangGraph 平台自动持久化, 依赖 thread_id)
graph = _build_graph().compile(name="world_builder")
