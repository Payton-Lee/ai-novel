"""SettingStudioState — 设定工作台状态."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class SettingStudioState(TypedDict, total=False):
    """设定工作台状态.

    project_id 指向共享设定库 (ProjectStore); 各板块快照每轮从库注入上下文。
    """

    messages: Annotated[list[AnyMessage], add_messages]
    project_id: str  # 当前项目 (设定库)
    genre: str
    premise: str
    store_snapshot: str  # 从库注入的完整设定快照 (工作台的"记忆")
