"""DirectorState — 创作导演状态 (各阶段产物累积)."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class DirectorState(TypedDict, total=False):
    """创作导演状态.

    各阶段产物累积在 state, 避免重复生成; 用户可随时调整任一阶段。
    """

    messages: Annotated[list[AnyMessage], add_messages]
    goal: str  # 用户目标 (如 "番茄风都市修仙50万字")
    genre: str  # 题材
    style: str  # "fanqie" / 自定义
    style_samples: str  # 用户提供的风格样本 (可选)

    stage: str  # 当前阶段: idea→world→character→outline→serial→package

    idea: str  # 选题/一句话概念
    world_bible: str  # 世界观
    characters: str  # 人物卡片
    full_outline: str  # 完整大纲
    story_id: str  # 连载 story_id
    serial_ready: str  # 连载准备提示 (含大纲列表)
    product: str  # 包装产物 (书名/简介)
