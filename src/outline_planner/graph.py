"""大纲规划 Agent — 对话式迭代主图.

图结构 (与 world_builder 同构, chat loop + 持久化):
    START → outline_planner → (tools_condition) → tools → outline_planner → ... → END

多轮对话依赖 thread_id, 由 LangGraph 平台自动持久化。
outline_draft 每轮从 HumanMessage 现场组装, 注入系统提示词作为稳定记忆。
"""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from novel.llm_factory import get_llm_from_config
from outline_planner.prompts import OUTLINE_PLANNER_SYSTEM_PROMPT
from outline_planner.state import OutlinePlannerState
from outline_planner.tools import OUTLINE_PLANNER_TOOLS, generate_full_outline


def _assemble_draft(messages: list[AnyMessage]) -> str:
    """从对话历史中组装大纲草稿 (只取用户真实输入)."""
    parts: list[str] = []
    for m in messages:
        if m.type == "human":
            text = str(m.content).strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def outline_planner_node(
    state: OutlinePlannerState, config: Optional[RunnableConfig] = None
) -> dict:
    """主对话节点: 结合大纲草稿记忆调用 LLM, 支持工具调用."""
    llm = get_llm_from_config(config)

    draft = _assemble_draft(state.get("messages", []))
    system = OUTLINE_PLANNER_SYSTEM_PROMPT

    # 注入已提供的素材 (世界观/人物), 作为稳定上下文
    context_bits = []
    if state.get("genre"):
        context_bits.append(f"题材: {state['genre']}")
    if state.get("premise"):
        context_bits.append(f"故事前提: {state['premise']}")
    if state.get("world_bible"):
        context_bits.append(f"世界观圣经:\n{state['world_bible']}")
    if state.get("characters"):
        chars = state["characters"]
        bits = []
        for c in chars:
            if isinstance(c, dict):
                bits.append(f"- {c.get('name','?')} ({c.get('role','配角')}): {c.get('personality','')}")
            else:
                bits.append(f"- {c}")
        context_bits.append("人物:\n" + "\n".join(bits))
    if context_bits:
        system += "\n\n## 作者已提供的素材\n" + "\n\n".join(context_bits)

    if draft:
        system += (
            "\n\n## 当前大纲草稿 (作者对话中确认的内容, 供你保持一致性)\n"
            f"{draft}\n"
        )

    llm_with_tools = llm.bind_tools(OUTLINE_PLANNER_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )

    return {"messages": [ai_msg], "outline_draft": draft}


def tools_node(
    state: OutlinePlannerState, config: Optional[RunnableConfig] = None
) -> dict:
    """工具执行节点; 若导出了完整大纲, 同步写入状态."""
    node = ToolNode(OUTLINE_PLANNER_TOOLS)
    result = node.invoke(state)

    full_outline = None
    for m in reversed(state.get("messages", [])):
        if m.type != "ai":
            continue
        for tc in getattr(m, "tool_calls", []) or []:
            if tc["name"] == generate_full_outline.name:
                for rm in result.get("messages", []):
                    if rm.type == "tool" and rm.tool_call_id == tc["id"]:
                        full_outline = rm.content
                        break
        if full_outline:
            break

    if full_outline:
        result["full_outline"] = full_outline
    return result


def _build_graph() -> StateGraph:
    """构建大纲规划器 StateGraph."""
    builder = StateGraph(OutlinePlannerState)

    builder.add_node("outline_planner", outline_planner_node)
    builder.add_node("tools", tools_node)

    builder.add_edge(START, "outline_planner")
    builder.add_conditional_edges(
        "outline_planner",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "outline_planner")

    return builder


# 编译图 — 无自定义 checkpointer (LangGraph 平台自动持久化, 依赖 thread_id)
graph = _build_graph().compile(name="outline_planner")
