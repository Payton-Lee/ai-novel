"""设定工作台主图 — 对话式, 每轮读写项目设定库 (多次对话持续完善).

图: START → studio(读库+对话) → tools_condition → tools(执行+落库) → studio → ...
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from character_builder.render import render_relationship_html
from novel.llm_factory import get_llm_from_config
from setting_studio.prompts import SETTING_STUDIO_PROMPT
from setting_studio.project_store import SECTION_LABELS, ProjectStore, get_project_store
from setting_studio.state import SettingStudioState
from setting_studio.tools import SETTING_STUDIO_TOOLS

PROJECTS_OUTPUT = Path(__file__).resolve().parents[2] / "output" / "projects"


def _format_snapshot(settings: dict, genre: str = "", premise: str = "") -> str:
    """把库内各板块格式化为快照注入上下文."""
    lines = [f"题材: {genre or '(未设)'}", f"前提: {premise or '(未设)'}", ""]
    for section in ("world", "characters", "relationships", "timeline", "conflicts", "outline"):
        label = SECTION_LABELS.get(section, section)
        content = (settings.get(section) or "").strip()
        if content:
            lines.append(f"\n## {label}\n{content[:2000]}")
        else:
            lines.append(f"\n## {label}\n(尚未设定)")
    return "\n".join(lines)


def studio_node(state: SettingStudioState, config: Optional[RunnableConfig] = None) -> dict:
    """主对话节点: 读项目设定库 → 注入快照 → 调 LLM 决策工具."""
    pid = state.get("project_id", "")
    if not pid:
        raise ValueError("需要 project_id 指定项目设定库")

    store = get_project_store(pid)
    # 确保项目存在
    if not store.get_project(pid):
        store.create_project(pid, {"genre": state.get("genre", ""), "premise": state.get("premise", "")})
    settings = store.all_settings(pid)
    store.close()

    snapshot = _format_snapshot(settings, state.get("genre", ""), state.get("premise", ""))
    system = SETTING_STUDIO_PROMPT + f"\n\n# 当前项目设定库 (PID: {pid})\n{snapshot}"

    llm = get_llm_from_config(config)
    llm_with_tools = llm.bind_tools(SETTING_STUDIO_TOOLS)
    ai_msg: AIMessage = llm_with_tools.invoke(
        [SystemMessage(content=system), *state.get("messages", [])]
    )
    return {"messages": [ai_msg], "store_snapshot": snapshot}


def _mermaid_from_text(text: str) -> str:
    m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    for line in text.splitlines():
        if re.match(r"^(graph|flowchart)\s+(TD|TB|LR)", line.strip()):
            return text.strip()
    return ""


def _persist_tool_results(
    state: SettingStudioState,
    tool_calls: list[dict],
    tool_msgs: dict[str, Any],
) -> dict:
    """按工具名把结果落库 + 渲染 HTML + 记变更日志."""
    pid = state.get("project_id", "")
    store = get_project_store(pid)
    if not store.get_project(pid):
        store.create_project(pid, {"genre": state.get("genre", ""), "premise": state.get("premise", "")})

    updates: dict[str, str] = {}
    html_note = ""

    try:
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            tm = tool_msgs.get(tc.get("id"))
            content = str(tm.content).strip() if tm else ""
            if not content:
                continue

            if name == "record_setting":
                # record_setting 的真实内容在 args['content'] (工具返回的是占位符)
                section = str(args.get("section", ""))
                real_content = str(args.get("content", "")).strip()
                if section in SECTION_LABELS and real_content:
                    store.save_setting(pid, section, real_content, change=f"更新{section}板块")
                    updates[section] = real_content
            elif name == "generate_timeline":
                store.save_setting(pid, "timeline", content, change="生成时间线")
                updates["timeline"] = content
            elif name == "generate_character_card":
                # 追加描写卡到 characters 板块
                old = store.get_setting(pid, "characters")
                new = (old + "\n\n" + content if old else content).strip()
                store.save_setting(pid, "characters", new, change="新增人物描写卡")
                updates["characters"] = new
            elif name == "deduce_conflicts":
                store.save_setting(pid, "conflicts", content, change="推演冲突")
                updates["conflicts"] = content
            elif name == "build_relationship_graph":
                store.save_setting(pid, "relationships", content, change="生成关系图")
                updates["relationships"] = content
                mermaid = _mermaid_from_text(content)
                if mermaid:
                    PROJECTS_OUTPUT.mkdir(parents=True, exist_ok=True)
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    html = render_relationship_html(mermaid, title=f"关系图_{pid}")
                    if html:
                        html_note = f"\n\n📄 关系图已生成: `{html}`"
            elif name == "export_doc":
                out_dir = PROJECTS_OUTPUT / pid
                out_dir.mkdir(parents=True, exist_ok=True)
                f = out_dir / "setting.md"
                f.write_text(content, encoding="utf-8")
                html_note += f"\n\n📄 完整设定文档已导出: `{f}`"
    finally:
        store.close()

    result: dict = {}
    if updates:
        result.update(updates)
    if html_note:
        result["store_snapshot"] = html_note
    return result


def tools_node(state: SettingStudioState, config: Optional[RunnableConfig] = None) -> dict:
    """工具执行 + 落库."""
    node = ToolNode(SETTING_STUDIO_TOOLS)
    result = node.invoke(state)

    # 收集本轮 tool_calls (从最近的 AI 消息)
    tool_calls: list[dict] = []
    for m in reversed(state.get("messages", [])):
        if m.type == "ai":
            tool_calls = [tc for tc in getattr(m, "tool_calls", []) or []]
            break

    tool_msgs = {rm.tool_call_id: rm for rm in result.get("messages", []) if rm.type == "tool"}
    persist = _persist_tool_results(state, tool_calls, tool_msgs)
    if persist:
        result.update(persist)
    return result


def _build_graph() -> StateGraph:
    builder = StateGraph(SettingStudioState)
    builder.add_node("studio", studio_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "studio")
    builder.add_conditional_edges(
        "studio",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "studio")
    return builder


# 平台版本 — 无自定义 checkpointer (LangGraph 平台持久化; 设定本身存 ProjectStore)
graph = _build_graph().compile(name="setting_studio")


def get_local_graph():
    """本地 python 脚本多轮持久化用 (惰性创建, 避免 langgraph dev 检测到 checkpointer)."""
    from langgraph.checkpoint.memory import MemorySaver
    return _build_graph().compile(checkpointer=MemorySaver(), name="setting_studio_local")
