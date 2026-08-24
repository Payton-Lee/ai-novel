"""大纲细化 Agent — 将粗略大纲拆解为可执行的场景分镜."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from typing import Optional

from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config
from novel.prompts import OUTLINE_SYSTEM_PROMPT
from novel.state import NovelState


def outline_agent(state: NovelState, config: Optional[RunnableConfig] = None) -> dict:
    """将用户的章节大纲细化为 3-5 个具体场景, 含冲突/钩子/伏笔设计.

    输入: genre, premise, world_setting, characters, chapter_outline
    输出: detailed_outline, plot_tracker
    """
    llm = get_llm_from_config(config)

    # 构建角色摘要
    chars = state.get("characters", [])
    char_summary = "\n".join(
        f"- {c.get('name', '未知')} ({c.get('role', '配角')}): {c.get('personality', '')}"
        for c in chars
    )

    user_prompt = f"""请根据以下信息, 细化本章大纲:

## 题材
{state.get('genre', '未指定')}

## 故事前提
{state.get('premise', '')}

## 世界观
{state.get('world_setting', '')}

## 人物
{char_summary}

## 本章大纲
{state.get('chapter_outline', '')}

## 前情摘要
{state.get('prev_chapter_summary', '这是第一章, 无前情。')}

请按照系统提示中的格式输出细化后的大纲。"""

    resp = llm.invoke([
        SystemMessage(content=OUTLINE_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    outline_text = resp.content

    # 提取伏笔信息
    plot_tracker = _extract_plot_threads(outline_text)

    return {
        "detailed_outline": outline_text,
        "plot_tracker": plot_tracker,
    }


def _extract_plot_threads(outline_text: str) -> list[dict]:
    """从大纲文本中提取伏笔条目."""
    threads: list[dict] = []
    in_foreshadow = False
    for line in outline_text.splitlines():
        stripped = line.strip()
        if "伏笔" in stripped and ("操作" in stripped or "##" in stripped):
            in_foreshadow = True
            continue
        if in_foreshadow and stripped.startswith("- 埋设"):
            content = stripped.replace("- 埋设:", "").replace("- 埋设：", "").strip()
            if content:
                threads.append({"thread": content, "introduced_chapter": 0, "status": "unresolved"})
        elif in_foreshadow and stripped.startswith("- 回收"):
            content = stripped.replace("- 回收:", "").replace("- 回收：", "").strip()
            if content:
                threads.append({"thread": content, "introduced_chapter": 0, "status": "resolved"})
        elif in_foreshadow and stripped.startswith("##"):
            in_foreshadow = False
    return threads
