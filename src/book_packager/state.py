"""BookPackagerState — 发布包装器状态."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class BookPackagerState(TypedDict, total=False):
    """发布包装器状态."""

    messages: Annotated[list[AnyMessage], add_messages]
    book_info: str  # 作品信息 (题材/前提/主角/卖点等, 输入)
