"""OutlinePlannerState — 大纲规划器的状态定义."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from novel.state import CharacterCard


class OutlinePlannerState(TypedDict, total=False):
    """大纲规划器状态.

    输入: 题材/前提/世界观/人物 (可来自 world_builder 导出)。
    对话: messages 累积历史, outline_draft 维护大纲草稿。
    输出: full_outline — 分卷分章完整大纲, 供 novel 图逐章使用。
    """

    messages: Annotated[list[AnyMessage], add_messages]  # 对话历史
    genre: str  # 题材 (输入)
    premise: str  # 故事前提 (输入)
    world_bible: str  # 世界观圣经 (输入, 来自 world_builder)
    characters: list[CharacterCard]  # 人物列表 (输入)
    outline_draft: str  # 累积的大纲草稿 (对话中维护)
    full_outline: str  # 最终导出的完整大纲 (输出)
    target_chapters: int  # 目标总章数 (可选)
