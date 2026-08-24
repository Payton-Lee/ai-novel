"""每章字数校验 — 写作后统计字数, 超目标范围自动压缩/扩写."""

from __future__ import annotations

import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config


def count_words(text: str) -> int:
    """统计正文字数 (中文字符含标点 + 英文单词)."""
    chinese = sum(
        1 for ch in text
        if 0x4E00 <= ord(ch) <= 0x9FFF  # CJK 统一汉字
        or 0x3400 <= ord(ch) <= 0x4DBF  # CJK 扩展A
        or 0x3000 <= ord(ch) <= 0x303F  # CJK 标点
        or 0xFF00 <= ord(ch) <= 0xFFEF  # 全角标点
    )
    english = len(re.findall(r"[a-zA-Z]+", text))
    return chinese + english


_COMPRESS_PROMPT = """你是章节压缩师。当前章节 **{words}字**, 目标压缩到 **{target}字**。

要求:
1. 保留: 核心情节推进、关键对话、章末钩子、人物状态变化
2. 删减: 冗余景物描写、重复的心理活动、拖沓的过渡段落
3. 保持文风一致 (短句、快节奏、番茄风格)
4. 直接输出压缩后的完整章节, 不要解释"""

_EXPAND_PROMPT = """你是章节扩写师。当前章节 **{words}字**, 目标扩写到 **{target}字**。

要求:
1. 在现有情节基础上补充: 场景细节、人物对话、动作反应、必要的内心活动
2. 不新增剧情事件/人物, 不改变主线走向
3. 保持文风一致 (短句、快节奏、番茄风格), 不能注水
4. 直接输出扩写后的完整章节, 不要解释"""


# 调整达标容差: 目标范围 ±15%
TOLERANCE = 0.15
# 最多迭代次数 (每章调整的 LLM 调用上限)
MAX_ITERATIONS = 3


def adjust_to_target(
    content: str,
    min_words: int,
    max_words: int,
    config: Optional[RunnableConfig] = None,
) -> str:
    """把章节调整到目标字数范围 (迭代逼近); 已达标则原样返回.

    Args:
        content: 章节正文
        min_words / max_words: 目标字数范围
        config: LangGraph config

    Returns:
        调整后的章节 (或原章节, 若已在容差内)。
    """
    if not content:
        return content

    current = content
    words = count_words(current)

    for _ in range(MAX_ITERATIONS):
        if min_words <= words <= max_words:
            return current
        # 在容差内视为达标 (±15%)
        if min_words * (1 - TOLERANCE) <= words <= max_words * (1 + TOLERANCE):
            return current

        if words > max_words:
            target = f"{max_words}-{max_words}"
            prompt = _COMPRESS_PROMPT.format(words=words, target=target)
            system = "你是章节压缩师。"
        else:
            target = f"{min_words}-{min_words}"
            prompt = _EXPAND_PROMPT.format(words=words, target=target)
            system = "你是章节扩写师。"

        try:
            llm = get_llm_from_config(config)
            resp = llm.invoke([
                SystemMessage(content=system + "只输出调整后的章节正文。"),
                HumanMessage(content=prompt + f"\n\n(当前实际 {words}字)\n\n## 原文\n" + current),
            ])
            new_text = str(resp.content).strip()
            new_words = count_words(new_text)
            # 调整后更差或无变化则停止
            if new_words <= 100 or abs(new_words - target_words(target)) >= abs(words - target_words(target)):
                return current
            current, words = new_text, new_words
        except Exception:
            return current

    return current


def target_words(t: str) -> int:
    """从 '2000-2200' 取目标中间值."""
    try:
        parts = t.split("-")
        return (int(parts[0]) + int(parts[1])) // 2
    except Exception:
        return 2000
