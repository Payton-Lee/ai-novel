"""发布包装 Agent — 对话式主图 (chat loop, 平台自动持久化)."""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from book_packager.prompts import PACKAGER_SYSTEM_PROMPT
from book_packager.state import BookPackagerState
from book_packager.tools import PACKAGER_TOOLS
from novel.llm_factory import get_llm_from_config


def packager_node(state: BookPackagerState, config: Optional[RunnableConfig] = None) -> dict:
    """主对话节点."""
    llm = get_llm_from_config(config)
    system = PACKAGER_SYSTEM_PROMPT
    if state.get("book_info"):
        system += f"\n\n## 作品信息\n{state['book_info']}"

    llm_with_tools = llm.bind_tools(PACKAGER_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )
    return {"messages": [ai_msg]}


def _build_graph() -> StateGraph:
    builder = StateGraph(BookPackagerState)
    builder.add_node("packager", packager_node)
    builder.add_node("tools", ToolNode(PACKAGER_TOOLS))
    builder.add_edge(START, "packager")
    builder.add_conditional_edges(
        "packager",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "packager")
    return builder


graph = _build_graph().compile(name="book_packager")
