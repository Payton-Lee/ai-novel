"""CharacterBuilderState — 人物定义器的状态定义."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from novel.state import CharacterCard


class CharacterBuilderState(TypedDict, total=False):
    """人物定义器状态.

    输入: 题材/前提/世界观/大纲/已有角色 (背景)。
    对话: messages 累积历史, char_draft 维护人物设定草稿。
    输出: character_cards (供 novel 图), relationship_graph + html_path (关系图)。
    """

    messages: Annotated[list[AnyMessage], add_messages]  # 对话历史
    genre: str  # 题材 (输入)
    premise: str  # 故事前提 (输入)
    world_bible: str  # 世界观圣经 (背景, 可选)
    outline_draft: str  # 大纲 (背景, 可选)
    characters: list[CharacterCard]  # 已有角色 (可选)
    char_draft: str  # 累积的人物设定草稿 (对话中维护)
    character_cards: str  # 导出的人物卡片集 (输出, 供 novel 图)
    relationship_graph: str  # 人物关系图 Mermaid 代码 (输出)
    html_path: str  # 生成的 HTML 关系图文件路径 (输出)
