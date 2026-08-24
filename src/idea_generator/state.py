"""IdeaGeneratorState — 创意生成器状态."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class IdeaGeneratorState(TypedDict, total=False):
    """创意生成器状态."""

    messages: Annotated[list[AnyMessage], add_messages]
    keywords: str  # 题材偏好/关键词/限制 (输入)
