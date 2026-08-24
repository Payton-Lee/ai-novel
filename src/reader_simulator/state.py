"""ReaderSimulatorState — 读者模拟器状态."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ReaderSimulatorState(TypedDict, total=False):
    """读者模拟器状态.

    输入: 题材 + 目标读者画像; 对话中喂入章节文本进行读者视角评估。
    """

    messages: Annotated[list[AnyMessage], add_messages]  # 对话历史
    genre: str  # 题材 (输入)
    audience: str  # 目标读者画像 (如 "追爽文的男频读者, 追读率高, 受不了拖沓")
