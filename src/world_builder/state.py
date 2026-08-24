"""WorldBuilderState — 世界观编辑器的状态定义."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class WorldBuilderState(TypedDict, total=False):
    """世界观编辑器状态.

    多轮对话通过 messages 累积历史; world_draft 维护已补全的设定摘要;
    world_bible 是最终导出产物 (供 novel 图直接使用)。
    """

    messages: Annotated[list[AnyMessage], add_messages]  # 完整对话历史
    genre: str  # 题材 (输入, 如 "都市修仙")
    premise: str  # 故事前提 (输入, 如 "主角从底层崛起")
    world_draft: str  # 累积的世界观设定草稿 (对话中增量维护)
    world_bible: str  # 最终导出的世界圣经 (输出)
