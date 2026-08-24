"""创意生成 Agent — 对话式主图 (chat loop, 平台自动持久化)."""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from idea_generator.prompts import IDEA_SYSTEM_PROMPT
from idea_generator.state import IdeaGeneratorState
from idea_generator.tools import IDEA_TOOLS
from novel.llm_factory import get_llm_from_config


def idea_node(state: IdeaGeneratorState, config: Optional[RunnableConfig] = None) -> dict:
    """主对话节点."""
    llm = get_llm_from_config(config)
    system = IDEA_SYSTEM_PROMPT
    if state.get("keywords"):
        system += f"\n\n## 作者偏好/关键词\n{state['keywords']}"

    llm_with_tools = llm.bind_tools(IDEA_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )
    return {"messages": [ai_msg]}


def _build_graph() -> StateGraph:
    builder = StateGraph(IdeaGeneratorState)
    builder.add_node("idea", idea_node)
    builder.add_node("tools", ToolNode(IDEA_TOOLS))
    builder.add_edge(START, "idea")
    builder.add_conditional_edges(
        "idea",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "idea")
    return builder


graph = _build_graph().compile(name="idea_generator")
