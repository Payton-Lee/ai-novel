"""工具函数 — 禁词检测、字数统计、文本质量辅助评估."""

from __future__ import annotations

import re

from novel.prompts import BANNED_PHRASES


def check_banned_phrases(text: str) -> list[dict[str, str | int]]:
    """检测文本中的禁词, 返回发现列表.

    Returns:
        [{"phrase": "禁词", "count": 2, "positions": ["第X段..."]}, ...]
    """
    findings: list[dict[str, str | int]] = []
    for phrase in BANNED_PHRASES:
        if "…" in phrase:
            continue  # 跳过含省略号的模式
        count = text.count(phrase)
        if count > 0:
            findings.append({"phrase": phrase, "count": count})
    return findings


def check_emotion_labels(text: str) -> list[str]:
    """检测情感标签化表达 (如 "感到愤怒"), 返回建议替换的条目."""
    issues: list[str] = []
    patterns = [
        (r"感到[^，。！？\n]{1,8}", "感到XXX"),
        (r"觉得[^，。！？\n]{1,8}起来", "觉得XXX起来"),
        (r"内心[^，。！？\n]{1,6}(涌起|充满|感到)", "内心涌起XXX"),
    ]
    for pattern, desc in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            issues.append(f'"{m}" — 应改为身体感受描写 (禁止{desc}模式)')
    return issues


def count_words(text: str) -> int:
    """统计中文字数 (粗略: 中文字符 + 英文单词)."""
    # 中文字符数
    chinese = sum(1 for ch in text if "一" <= ch <= "鿿")
    # 英文单词数
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    return chinese + english_words


def check_dialogue_ratio(text: str) -> float:
    """计算对话占比 (对话内容 / 总内容)."""
    # 匹配中文引号内的对话
    dialogue_chars = 0
    for m in re.finditer(r"[""「」]([^""「」]*)[""「」]", text):
        dialogue_chars += len(m.group(1))

    total = len(text)
    if total == 0:
        return 0.0
    return dialogue_chars / total


def quality_report(text: str) -> dict:
    """生成快速质量报告 (无需调用 LLM).

    Returns:
        {
            "word_count": int,
            "banned_phrases": [...],
            "emotion_labels": [...],
            "dialogue_ratio": float,
            "issues_count": int,
        }
    """
    banned = check_banned_phrases(text)
    emotions = check_emotion_labels(text)
    return {
        "word_count": count_words(text),
        "banned_phrases": banned,
        "emotion_labels": emotions,
        "dialogue_ratio": round(check_dialogue_ratio(text), 2),
        "issues_count": len(banned) + len(emotions),
    }
