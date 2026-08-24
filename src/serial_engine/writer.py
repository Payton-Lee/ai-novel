"""连载引擎的章节写作 — 封装 novel 图 (复用 6-Agent 流水线)."""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from fanqie_style.guide import FANQIE_STYLE_GUIDE
from fanqie_style.profile import compact_profile
from novel.graph import graph as novel_graph
from novel.state import PlotThread


def write_chapter_with_novel(
    genre: str,
    premise: str,
    world_setting: str,  # 记忆上下文 (含世界设定 + 分层记忆)
    characters: list,
    chapter_outline: str,
    prev_chapter_summary: str,
    style_guide: str = "",
    plot_tracker: Optional[list[PlotThread]] = None,
    contract_text: str = "",
    extra_constraints: str = "",
    style_mode: str = "fanqie",
    style_profile: str = "",
    word_target: str = "",
    config: Optional[RunnableConfig] = None,
) -> dict:
    """调用 novel 图生成一章.

    Args:
        genre/premise/world_setting/characters: 故事设定 (每章重新注入, novel 图无状态)
        chapter_outline: 本章大纲
        prev_chapter_summary: 上一章摘要 (第一章为空)
        style_guide: 风格要求
        plot_tracker: 累积伏笔 (跨章传递, 用 _merge_list 追加)
        contract_text: 章节任务单文本 (写作硬约束, 并入大纲)
        extra_constraints: 额外约束 (如 reader 反馈重写), 并入 style_guide
        style_mode: "fanqie"(默认, 注入番茄指南) / "generic"(不注入)
        style_profile: 用户样本提取的风格画像 (可选, 追加到风格要求)
        config: LangGraph config (自动透传 LLM 选择)

    Returns:
        novel 图输出的字段: final_chapter / chapter_summary / chapter_word_count / quality_score 等
    """
    input_state: dict[str, Any] = {
        "genre": genre,
        "premise": premise,
        "world_setting": world_setting,
        "characters": characters or [],
        "chapter_outline": chapter_outline,
        "style_guide": style_guide,
    }
    # 注入番茄风格指南 (默认) + 用户风格画像
    if style_mode != "generic":
        style_bits = [FANQIE_STYLE_GUIDE]
        profile = compact_profile(style_profile)
        if profile:
            style_bits.append(profile)
        if word_target:
            style_bits.append(
                f"\n## 本章字数硬性目标\n- 本章必须控制在 **{word_target} 字** (正文, 含标点)。\n"
                f"- 不足则补充情节细节/对话; 超出则删减冗余。写作时按此目标规划内容量。"
            )
        input_state["style_guide"] = (style_guide + "\n\n" + "\n\n".join(style_bits)).strip()
    elif word_target:
        input_state["style_guide"] = (
            style_guide + f"\n\n## 本章字数硬性目标: {word_target} 字 (不足补充/超出删减)"
        ).strip()
    # 章节任务单并入大纲 (写作硬约束)
    if contract_text:
        input_state["chapter_outline"] = chapter_outline + "\n\n" + contract_text
    # 额外约束 (reader 反馈等) 并入风格要求
    if extra_constraints:
        input_state["style_guide"] = (input_state.get("style_guide", "") + "\n" + extra_constraints).strip()

    if prev_chapter_summary:
        input_state["prev_chapter_summary"] = prev_chapter_summary
    if plot_tracker:
        input_state["plot_tracker"] = plot_tracker

    return novel_graph.invoke(input_state, config=config)
