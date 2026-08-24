"""连载引擎记忆层 — 分层记忆组装与摘要压缩 (支撑几万章).

记忆层级 (参考 agent 记忆范式):
- 近景(工作记忆): 最近 N 章全文
- 中景(短期记忆): 当前卷摘要 + 最近几章摘要
- 远景(长期记忆): 全书摘要 (每卷重算)
- 动态状态: 人物状态 / 伏笔进度 / 势力关系 / 关键事件 (结构化)
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from novel.llm_factory import get_llm_from_config
from serial_engine.storage import StoryRepository

# 摘要压缩参数 (几万章时保证记忆可控)
RECENT_FULL_CHAPTERS = 3      # 近景: 最近 3 章全文
RECENT_SUMMARIES = 5          # 中景: 最近 5 章摘要
CHAPTERS_PER_VOLUME = 10      # 每 10 章聚合一卷摘要
CHAPTERS_PER_VOLUME_DEFAULT = 10


def assemble_memory(
    repo: StoryRepository,
    story_id: str,
    chapter_no: int,
    chapters_per_volume: int = CHAPTERS_PER_VOLUME,
) -> str:
    """组装分层记忆上下文, 注入下一章写作.

    Args:
        repo: 存储库
        story_id: 故事 ID
        chapter_no: 将要写的章节号 (记忆基于前面的章节)
        chapters_per_volume: 每卷章数 (与压缩参数一致)

    Returns:
        Markdown 格式的分层记忆上下文。
    """
    prev = chapter_no - 1
    if prev < 1:
        return ""

    parts: list[str] = []

    # ---------- 近景: 最近 3 章全文 ----------
    start = max(1, prev - RECENT_FULL_CHAPTERS + 1)
    recent = repo.get_chapters(story_id, start, prev)
    if recent:
        parts.append("## 近期章节全文 (最近几章, 注意文风/细节连续性)")
        for ch in recent:
            parts.append(f"\n### 第{ch['chapter_no']}章\n{ch.get('content','')}\n")

    # ---------- 中景: 当前卷摘要 + 最近 5 章摘要 ----------
    summaries = repo.get_summaries(story_id)
    chap_summaries = [
        summaries[k] for k in sorted(summaries, key=lambda x: x)
        if k.startswith("chapter_") and int(k.split("_")[1]) <= prev
    ][-RECENT_SUMMARIES:]
    if chap_summaries:
        parts.append("## 近期章节摘要")
        for s in chap_summaries:
            parts.append(f"- {s}")

    current_volume = (prev - 1) // chapters_per_volume + 1
    vol_summary = summaries.get(f"volume_{current_volume}")
    if vol_summary:
        parts.append(f"\n## 当前卷摘要 (第 {current_volume} 卷)")
        parts.append(vol_summary)

    # ---------- 远景: 全书摘要 ----------
    book_summary = summaries.get("book")
    if book_summary:
        parts.append("\n## 全书摘要 (远距离记忆)")
        parts.append(book_summary)

    # ---------- 动态状态 ----------
    dynamic = _assemble_dynamic_state(repo, story_id)
    if dynamic:
        parts.append(dynamic)

    return "\n\n".join(parts)


def _assemble_dynamic_state(repo: StoryRepository, story_id: str) -> str:
    """动态状态: 人物/伏笔/势力/关键事件 (结构化, 精简)."""
    parts: list[str] = []

    chars = repo.get_character_states(story_id)
    if chars:
        parts.append("## 人物当前状态")
        lines = []
        for c in chars:
            try:
                state = json.loads(c["state_json"])
                lines.append(f"- {c['name']} (更新于第{c['updated_chapter']}章): {state.get('status','')}")
            except json.JSONDecodeError:
                lines.append(f"- {c['name']}: {c['state_json']}")
        parts.append("\n".join(lines))

    # 谁知道什么 — 长文最易写崩的信息墙 (防 OOC / 防提前透传)
    know_lines = []
    for c in chars:
        try:
            state = json.loads(c["state_json"])
            known = state.get("known_info") or []
            unknown = state.get("unknown_info") or []
            bits = []
            if known:
                bits.append("已知: " + "; ".join(known))
            if unknown:
                bits.append("未知: " + "; ".join(unknown))
            if bits:
                know_lines.append(f"- {c['name']}: {' | '.join(bits)}")
        except json.JSONDecodeError:
            continue
    if know_lines:
        parts.append("## 谁知道什么 (每个角色已知/未知 — 角色只能说自己该知道的事)")
        parts.append("\n".join(know_lines))

    threads = repo.get_plot_threads(story_id)
    open_threads = [t for t in threads if t["status"] != "resolved"]
    if open_threads:
        parts.append("## 未回收伏笔")
        for t in open_threads:
            parts.append(f"- [{t['status']}] (第{t['introduced_chapter']}章埋): {t['thread']}")

    factions = repo.get_factions(story_id)
    if factions:
        parts.append("## 势力关系状态")
        for f in factions:
            try:
                state = json.loads(f["state_json"])
                parts.append(f"- {f['name']}: {state.get('status','')}")
            except json.JSONDecodeError:
                parts.append(f"- {f['name']}: {f['state_json']}")

    events = repo.get_key_events(story_id)
    if events:
        parts.append("## 关键事件回顾")
        for e in events[-20:]:  # 只保留最近 20 条, 防膨胀
            parts.append(f"- 第{e['chapter_no']}章: {e['event']}")

    return "\n\n".join(parts)


# ============================================================
# 摘要分层压缩
# ============================================================

_VOLUME_ROLLUP_PROMPT = """你是小说的摘要压缩器。请把下面一个卷内的章节摘要, 压缩成一段 200 字以内的**卷摘要**, 保留: 卷内主线推进、重要事件、人物状态变化、已埋与已回收的伏笔。去掉细节, 只留骨架。

章节摘要:
{chapter_summaries}

卷摘要:"""

_BOOK_ROLLUP_PROMPT = """你是小说的摘要压缩器。请把下面各卷摘要, 压缩成一段 300 字以内的**全书摘要**, 保留: 核心主线、主角成长阶段、尚未回收的关键伏笔、当前冲突焦点。去掉已完成的情节细节。

各卷摘要:
{volume_summaries}

全书摘要:"""


def _llm_summarize(prompt: str, system: str) -> str:
    """调用默认配置的 LLM 生成摘要."""
    llm = get_llm_from_config()
    resp = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ])
    return resp.content.strip()


def save_chapter_summary(repo: StoryRepository, story_id: str, chapter_no: int, summary: str) -> None:
    """存章节摘要 (来自 novel 输出的 chapter_summary)."""
    if summary:
        repo.save_summary(story_id, f"chapter_{chapter_no}", summary)


def rollup_volume_summary(
    repo: StoryRepository, story_id: str, chapter_no: int, chapters_per_volume: int = CHAPTERS_PER_VOLUME
) -> None:
    """每 chapters_per_volume 章, 把该卷章节摘要聚合成卷摘要, 并删除已聚合的章节摘要 (防膨胀)."""
    volume_no = (chapter_no - 1) // chapters_per_volume + 1
    vol_key = f"volume_{volume_no}"
    if repo.get_summary(story_id, vol_key):
        return  # 已聚合过

    chap_range = range((volume_no - 1) * chapters_per_volume + 1, volume_no * chapters_per_volume + 1)
    chap_sums = []
    for n in chap_range:
        s = repo.get_summary(story_id, f"chapter_{n}")
        if s:
            chap_sums.append(f"第{n}章: {s}")
    if not chap_sums:
        return

    vol_summary = _llm_summarize(
        _VOLUME_ROLLUP_PROMPT.format(chapter_summaries="\n".join(chap_sums)),
        "你是严谨的小说摘要压缩器。",
    )
    repo.save_summary(story_id, vol_key, vol_summary)
    # 删除已聚合的章节摘要
    for n in chap_range:
        repo.save_summary(story_id, f"chapter_{n}", "")

    # 卷数变化时更新全书摘要
    rollup_book_summary(repo, story_id, chapters_per_volume)


def rollup_book_summary(repo: StoryRepository, story_id: str, chapters_per_volume: int = CHAPTERS_PER_VOLUME) -> None:
    """把全部卷摘要聚合为全书摘要."""
    summaries = repo.get_summaries(story_id)
    vols = sorted(
        (k for k in summaries if k.startswith("volume_") and summaries[k]),
        key=lambda x: int(x.split("_")[1]),
    )
    if not vols:
        return
    vol_text = "\n".join(f"第{k.split('_')[1]}卷: {summaries[k]}" for k in vols)
    book_summary = _llm_summarize(
        _BOOK_ROLLUP_PROMPT.format(volume_summaries=vol_text),
        "你是严谨的小说摘要压缩器。",
    )
    repo.save_summary(story_id, "book", book_summary)
