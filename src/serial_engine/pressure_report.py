"""连载压力测试四指标分析 — 人物OOC / 伏笔遗忘 / 剧情重复 / 章节套路化.

规则检测 (便宜) 默认开启; LLM 深度检测 (人物OOC/套路化) 需 --deep 开启。
"""

from __future__ import annotations

import json
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from novel.llm_factory import get_llm_from_config
from serial_engine.storage import StoryRepository

# 伏笔遗忘判定: 未回收伏笔连续超过该章数未提及
THREAD_STALE_THRESHOLD = 5
# 剧情重复阈值 (Jaccard 相似度)
REPETITION_THRESHOLD = 0.45


# ============================================================
# 1. 剧情重复 (相邻章 n-gram Jaccard)
# ============================================================

def _ngrams(text: str, n: int = 3) -> set[str]:
    text = re.sub(r"\s+", "", text)
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def check_repetition(chapters: list[dict]) -> list[dict]:
    """相邻章节内容相似度 (取每章首尾片段), 超过阈值报警."""
    findings = []
    for i in range(len(chapters) - 1):
        a, b = chapters[i], chapters[i + 1]
        frag_a = (a.get("content", "")[:400] + a.get("content", "")[-300:])
        frag_b = (b.get("content", "")[:400] + b.get("content", "")[-300:])
        sim = _jaccard(_ngrams(frag_a), _ngrams(frag_b))
        if sim >= REPETITION_THRESHOLD:
            findings.append({
                "chapter_from": a["chapter_no"], "chapter_to": b["chapter_no"],
                "similarity": round(sim, 2), "level": "high" if sim >= 0.6 else "medium",
            })
    return findings


# ============================================================
# 2. 伏笔遗忘 (未回收伏笔连续 N 章未提及)
# ============================================================

def check_forgotten_threads(
    repo: StoryRepository, story_id: str, threads: list[dict], total_chapters: int
) -> list[dict]:
    """未回收伏笔在最近 N 章摘要/事件中未出现的标记为遗忘风险."""
    summaries = repo.get_summaries(story_id)
    chapter_sums = [
        (int(k.split("_")[1]), v) for k, v in summaries.items()
        if k.startswith("chapter_") and v
    ]
    chapter_sums.sort()

    findings = []
    for t in threads:
        if t["status"] == "resolved":
            continue
        last_seen = t.get("updated_chapter", t.get("introduced_chapter", 0))
        # 检查该伏笔关键词是否在后续摘要中出现
        keyword = re.sub(r"[（(【\[].*?[)）】\]]", "", t["thread"])[:12]
        stale = 0
        for ch_no, s in chapter_sums:
            if ch_no > last_seen and keyword and keyword in s:
                stale = 0
                last_seen = ch_no
            elif ch_no > last_seen:
                stale += 1
        if stale >= THREAD_STALE_THRESHOLD or (total_chapters - last_seen) >= THREAD_STALE_THRESHOLD:
            findings.append({
                "thread": t["thread"], "status": t["status"],
                "last_mentioned_chapter": last_seen,
                "stale_chapters": max(stale, total_chapters - last_seen),
            })
    return findings


# ============================================================
# 3 & 4. 人物OOC / 章节套路化 (LLM 深度检测, 可选)
# ============================================================

_OO_C_PROMPT = """你是连载质量审查员。对比相邻两章中同一角色的状态记录, 判断是否存在**人设崩塌 (OOC)**——即角色行为/认知/性格与已建立的设定明显矛盾。

第{from}章人物状态:
{from_states}

第{to}章人物状态:
{to_states}

只输出 JSON: {{"ooc": [{{"character": "角色", "issue": "矛盾描述", "evidence": "证据"}}]}}。没有则 "ooc": []。"""


def check_ooc_deep(character_states: list[dict]) -> list[dict]:
    """用 LLM 对比相邻章同角色状态, 检测 OOC."""
    # 按章分组
    by_chapter: dict[int, dict[str, str]] = {}
    for c in character_states:
        ch = c.get("updated_chapter", 0)
        try:
            state = json.loads(c["state_json"])
            by_chapter.setdefault(ch, {})[state.get("name", c["name"])] = state.get("status", "")
        except json.JSONDecodeError:
            continue

    findings = []
    chapters = sorted(by_chapter)
    try:
        llm = get_llm_from_config()
    except Exception:
        return findings

    for i in range(len(chapters) - 1):
        c_from, c_to = chapters[i], chapters[i + 1]
        common = set(by_chapter[c_from]) & set(by_chapter[c_to])
        if not common:
            continue
        from_states = "\n".join(f"{n}: {by_chapter[c_from][n]}" for n in common)
        to_states = "\n".join(f"{n}: {by_chapter[c_to][n]}" for n in common)
        try:
            resp = llm.invoke([
                SystemMessage(content="你是连载质量审查员。只输出合法 JSON。"),
                HumanMessage(content=_OO_C_PROMPT.format(
                    from_chapter=c_from, to_chapter=c_to,
                    from_states=from_states, to_states=to_states,
                )),
            ])
            m = re.search(r"\{[\s\S]*\}", str(resp.content))
            if m:
                data = json.loads(m.group(0))
                for item in data.get("ooc", []):
                    item["chapter_from"], item["chapter_to"] = c_from, c_to
                    findings.append(item)
        except Exception:
            continue
    return findings


_FORMULAIC_PROMPT = """你是连载质量审查员。分析下列章节的开头前 50 字和结尾钩子, 判断是否存在**套路化** (开头句式雷同、钩子模式重复、节奏模板化)。

章节片段:
{chapters}

只输出 JSON: {{"formulaic": [{{"chapter": "第X章", "pattern": "雷同模式", "suggestion": "改进建议"}}]}}。没有则 "formulaic": []。"""


def check_formulaic_deep(chapters: list[dict]) -> list[dict]:
    """用 LLM 判定章节开头/钩子的套路化."""
    if not chapters:
        return []
    samples = []
    for ch in chapters[:30]:  # 最多采样 30 章
        content = ch.get("content", "")
        head = content[:50].replace("\n", " ")
        tail = content[-80:].replace("\n", " ")
        samples.append(f"第{ch['chapter_no']}章 开头: {head} | 结尾: {tail}")
    prompt = _FORMULAIC_PROMPT.format(chapters="\n".join(samples))
    try:
        llm = get_llm_from_config()
        resp = llm.invoke([
            SystemMessage(content="你是连载质量审查员。只输出合法 JSON。"),
            HumanMessage(content=prompt),
        ])
        m = re.search(r"\{[\s\S]*\}", str(resp.content))
        if m:
            return json.loads(m.group(0)).get("formulaic", [])
    except Exception:
        pass
    return []


# ============================================================
# 汇总分析
# ============================================================

def analyze_story(repo: StoryRepository, story_id: str, deep: bool = False) -> dict:
    """对一部连载故事生成四指标压力报告."""
    chapters = repo.get_chapters(story_id, 1, 10**9)
    threads = repo.get_plot_threads(story_id)
    char_states = repo.get_character_states(story_id)
    total = len(chapters)

    report: dict = {
        "story_id": story_id,
        "total_chapters": total,
        "repetition": check_repetition(chapters),
        "forgotten_threads": check_forgotten_threads(repo, story_id, threads, total),
        "open_threads": sum(1 for t in threads if t["status"] != "resolved"),
        "resolved_threads": sum(1 for t in threads if t["status"] == "resolved"),
    }
    if deep:
        report["ooc"] = check_ooc_deep(char_states)
        report["formulaic"] = check_formulaic_deep(chapters)
    else:
        report["ooc"] = "需 --deep 开启 LLM 深度检测"
        report["formulaic"] = "需 --deep 开启 LLM 深度检测"

    # 汇总评级
    issues = len(report["repetition"]) + len(report["forgotten_threads"])
    if deep:
        issues += len(report["ooc"]) + len(report["formulaic"])
    if issues == 0:
        report["health"] = "良好"
    elif issues <= 3:
        report["health"] = "一般"
    else:
        report["health"] = "需关注"
    return report
