import os
import asyncio
import sys
import json
import importlib
from pathlib import Path
from typing import Annotated, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

load_dotenv()

SYSTEM_PROMPT = (
    "你是一个简洁、准确的中文助手。"
    "你支持按技能调用工具。"
    "可用技能会在系统上下文中给出；只在用户问题需要时调用对应工具。"
)
MCP_SERVERS_CONFIG = {
    "fetch": {
        "transport": "streamable_http",
        "url": "https://mcp.api-inference.modelscope.net/02877222d2c644/mcp",
    }
}


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _build_llm() -> Optional[object]:
    qwen_key = os.getenv("QWEN_KEY")
    if not qwen_key:
        return None
    try:
        from langchain_community.chat_models import ChatTongyi
    except ImportError:
        return None
    return ChatTongyi(model="qwen-plus", api_key=qwen_key)


llm = _build_llm()

# 让脚本直跑和图加载都能找到 ./skills
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
REGISTRY_PATH = CURRENT_DIR / "skills" / "registry.json"


def _load_registry() -> dict:
    try:
        with REGISTRY_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"skills": {}}


def _get_enabled_skill_names(config: Optional[RunnableConfig] = None) -> list[str]:
    registry = _load_registry().get("skills", {})
    default_enabled = [name for name, meta in registry.items() if meta.get("enabled", False)]
    if not config:
        return default_enabled
    configurable = (config or {}).get("configurable", {}) or {}
    runtime_selected = configurable.get("enabled_skills")
    if runtime_selected is None:
        return default_enabled
    if not isinstance(runtime_selected, list):
        return default_enabled
    return [x for x in runtime_selected if isinstance(x, str)]


def _load_registered_tools(enabled_skill_names: list[str]) -> list:
    skills = _load_registry().get("skills", {})
    tools: list = []
    for skill_name in enabled_skill_names:
        meta = skills.get(skill_name)
        if not meta:
            continue
        module_name = meta.get("module")
        tool_name = meta.get("tool")
        if not module_name or not tool_name:
            continue
        try:
            module = importlib.import_module(module_name)
            tool = getattr(module, tool_name)
            tools.append(tool)
        except Exception:
            continue
    return tools


def _init_mcp_tools() -> list:
    """初始化 MCP 工具；失败时返回空列表，避免影响主流程。"""
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except Exception:
        return []

    try:
        client = MultiServerMCPClient(MCP_SERVERS_CONFIG)
        return asyncio.run(client.get_tools())
    except Exception:
        return []


mcp_tools = _init_mcp_tools()


def _runtime_tools(config: Optional[RunnableConfig] = None) -> list:
    enabled = _get_enabled_skill_names(config)
    return [*_load_registered_tools(enabled), *mcp_tools]


def _fallback_reply(messages: list[AnyMessage]) -> str:
    human_messages = [m.content for m in messages if getattr(m, "type", "") == "human"]
    latest_user = human_messages[-1] if human_messages else ""
    if "上一句" in latest_user and len(human_messages) >= 2:
        return f"你上一句问的是：{human_messages[-2]}"
    return f"（本地回退）你刚才说：{latest_user}"


def chatbot(state: ChatState, config: RunnableConfig) -> ChatState:
    messages = state["messages"]
    runtime_tools = _runtime_tools(config)

    if llm is None:
        return {"messages": [AIMessage(content=_fallback_reply(messages))]}

    try:
        if runtime_tools:
            try:
                llm_with_tools = llm.bind_tools(runtime_tools)
            except Exception:
                llm_with_tools = llm
        else:
            llm_with_tools = llm

        enabled_skills = _get_enabled_skill_names(config)
        llm_messages = [SystemMessage(content=SYSTEM_PROMPT), *messages]
        if enabled_skills:
            llm_messages = [
                SystemMessage(content=f"当前启用技能: {', '.join(enabled_skills)}"),
                *llm_messages,
            ]
        response = llm_with_tools.invoke(llm_messages)
        return {"messages": [response]}
    except Exception:
        return {"messages": [AIMessage(content=_fallback_reply(messages))]}


def tools_router(state: ChatState, config: RunnableConfig) -> ChatState:
    runtime_tools = _runtime_tools(config)
    if not runtime_tools:
        return {}
    node = ToolNode(runtime_tools)
    return node.invoke(state)


builder = StateGraph(ChatState)
builder.add_node("chatbot", chatbot)
builder.add_node("tools", tools_router)
builder.add_edge(START, "chatbot")
builder.add_conditional_edges("chatbot", tools_condition, {"tools": "tools", "__end__": END})
builder.add_edge("tools", "chatbot")
graph = builder.compile()


def run_demo() -> None:
    turns = ["今天是几月几号？", "上一句我问了什么？"]
    config = {"configurable": {"enabled_skills": ["wind", "sse_calendar"]}}
    history: list[dict[str, str]] = []
    for i, user_input in enumerate(turns, start=1):
        history.append({"role": "user", "content": user_input})
        result = graph.invoke({"messages": history}, config=config)
        last = result["messages"][-1]
        history.append({"role": "assistant", "content": last.content})
        print(f"[第{i}轮] 用户: {user_input}")
        print(f"[第{i}轮] 助手: {last.content}\n")


if __name__ == "__main__":
    run_demo()
