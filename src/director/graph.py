"""一键串联导演 Agent — 对话式主图 (chat loop, 平台持久化)."""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from director.prompts import DIRECTOR_SYSTEM_PROMPT
from director.state import DirectorState
from director.tools import DIRECTOR_TOOLS
from novel.llm_factory import get_llm_from_config


def director_node(state: DirectorState, config: Optional[RunnableConfig] = None) -> dict:
    """主对话节点: 结合创作目标调用 LLM, 决策阶段工具."""
    llm = get_llm_from_config(config)
    system = DIRECTOR_SYSTEM_PROMPT

    context_bits = []
    if state.get("goal"):
        context_bits.append(f"创作目标: {state['goal']}")
    if state.get("genre"):
        context_bits.append(f"题材: {state['genre']}")
    if state.get("style"):
        context_bits.append(f"目标风格: {state['style']}")
    if state.get("stage"):
        context_bits.append(f"当前阶段: {state['stage']}")
    # 注入已累积的阶段产物 (核心: 防止导演"失忆"重复/脑补)
    if state.get("idea"):
        context_bits.append(f"已确定的选题: {str(state['idea'])[:600]}")
    if state.get("world_bible"):
        context_bits.append(f"已生成的世界观: {str(state['world_bible'])[:800]}")
    if state.get("characters"):
        context_bits.append(f"已生成的人物: {str(state['characters'])[:800]}")
    if state.get("full_outline"):
        context_bits.append(f"已生成的大纲: {str(state['full_outline'])[:800]}")
    if state.get("serial_ready"):
        context_bits.append(f"连载准备: {str(state['serial_ready'])[:300]}")
    if context_bits:
        system += "\n\n## 创作进度 (已确定的产物, 供你保持连续性, 不要再向用户索要)\n" + "\n".join(context_bits)

    llm_with_tools = llm.bind_tools(DIRECTOR_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )
    return {"messages": [ai_msg]}


# 工具结果 → 状态字段的映射 (阶段产物累积)
_TOOL_STATE_MAP = {
    "generate_idea": "idea",
    "build_world": "world_bible",
    "build_characters": "characters",
    "plan_outline": "full_outline",
    "prepare_serial": "serial_ready",
    "package_book": "product",
}


def tools_node(state: DirectorState, config: Optional[RunnableConfig] = None) -> dict:
    """工具执行节点; 把阶段产物累积到状态."""
    node = ToolNode(DIRECTOR_TOOLS)
    result = node.invoke(state)

    tool_msgs = {rm.tool_call_id: rm for rm in result.get("messages", []) if rm.type == "tool"}
    updates: dict = {}
    for m in reversed(state.get("messages", [])):
        if m.type != "ai":
            continue
        for tc in getattr(m, "tool_calls", []) or []:
            tm = tool_msgs.get(tc["id"])
            if not tm:
                continue
            field = _TOOL_STATE_MAP.get(tc["name"])
            if field:
                updates[field] = str(tm.content)

    if updates:
        result.update(updates)
    return result


def _build_graph() -> StateGraph:
    builder = StateGraph(DirectorState)
    builder.add_node("director", director_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "director")
    builder.add_conditional_edges(
        "director",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "director")
    return builder


# 平台版本 — 无自定义 checkpointer (LangGraph 平台自动持久化, 依赖 thread_id)
graph = _build_graph().compile(name="director")


def get_local_graph():
    """本地 python 脚本用的带持久化版本 (惰性创建, 避免 langgraph dev 检测到 checkpointer).

    用法:
        from director.graph import get_local_graph
        graph = get_local_graph()
    """
    return _build_graph().compile(checkpointer=MemorySaver(), name="director_local")
