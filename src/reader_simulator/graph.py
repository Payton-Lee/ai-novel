"""读者模拟 Agent — 对话式主图 (chat loop, 平台自动持久化)."""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from novel.llm_factory import get_llm_from_config
from reader_simulator.prompts import READER_SYSTEM_PROMPT
from reader_simulator.state import ReaderSimulatorState
from reader_simulator.tools import READER_TOOLS


def reader_node(state: ReaderSimulatorState, config: Optional[RunnableConfig] = None) -> dict:
    """主对话节点: 结合读者画像调用 LLM."""
    llm = get_llm_from_config(config)
    system = READER_SYSTEM_PROMPT

    context_bits = []
    if state.get("genre"):
        context_bits.append(f"题材: {state['genre']}")
    if state.get("audience"):
        context_bits.append(f"目标读者画像: {state['audience']}")
    if context_bits:
        system += "\n\n## 作者提供的上下文\n" + "\n".join(context_bits)

    llm_with_tools = llm.bind_tools(READER_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )
    return {"messages": [ai_msg]}


def _build_graph() -> StateGraph:
    builder = StateGraph(ReaderSimulatorState)
    builder.add_node("reader", reader_node)
    builder.add_node("tools", ToolNode(READER_TOOLS))
    builder.add_edge(START, "reader")
    builder.add_conditional_edges(
        "reader",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "reader")
    return builder


graph = _build_graph().compile(name="reader_simulator")
