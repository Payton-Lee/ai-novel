"""润色 Agent — 最终去AI味处理, 提升文学品质."""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config
from novel.prompts import POLISH_SYSTEM_PROMPT
from novel.state import NovelState


def polish_agent(state: NovelState, config: Optional[RunnableConfig] = None) -> dict:
    """根据审稿意见润色章节, 输出最终版本和摘要.

    输入: current_draft, review_feedback, character_cards, world_bible
    输出: final_chapter, chapter_summary, chapter_word_count
    """
    llm = get_llm_from_config(config)

    user_prompt = f"""请对以下章节进行最终润色:

## 当前草稿
{state.get('current_draft', '')}

## 审稿意见 (请针对性修改)
{state.get('review_feedback', '无特别意见, 做常规润色即可。')}

## 人物卡片 (确保语言风格一致)
{state.get('character_cards', '')}

## 世界圣经 (确保设定一致)
{state.get('world_bible', '')}

请按照系统提示要求:
1. 输出润色后的完整正文 (不要加章节标题)
2. 正文结束后, 另起一行写 "---摘要分隔线---"
3. 然后写 200 字以内的本章摘要 (供下一章参考)"""

    resp = llm.invoke([
        SystemMessage(content=POLISH_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    content = resp.content
    chapter_text, summary = _split_chapter_and_summary(content)

    # 统计正文字数 (去除空白和标点的大致中文字数)
    word_count = _count_chinese_chars(chapter_text)

    return {
        "final_chapter": chapter_text,
        "chapter_summary": summary,
        "chapter_word_count": word_count,
    }


def _split_chapter_and_summary(content: str) -> tuple[str, str]:
    """将润色输出拆分为正文和摘要."""
    separator = "---摘要分隔线---"
    if separator in content:
        parts = content.split(separator, 1)
        chapter = parts[0].strip()
        summary = parts[1].strip()
    else:
        # 如果没有分隔符, 尝试找"摘要"关键词
        lines = content.strip().splitlines()
        split_idx = len(lines)
        for i, line in enumerate(lines):
            if "摘要" in line and i > len(lines) // 2:
                split_idx = i
                break
        chapter = "\n".join(lines[:split_idx]).strip()
        summary = "\n".join(lines[split_idx:]).strip()
    return chapter, summary


def _count_chinese_chars(text: str) -> int:
    """统计中文字符数 (含中文标点)."""
    count = 0
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF  # CJK统一汉字
            or 0x3400 <= cp <= 0x4DBF  # CJK扩展A
            or 0x3000 <= cp <= 0x303F  # CJK标点
            or 0xFF00 <= cp <= 0xFFEF  # 全角标点
            or 0x2000 <= cp <= 0x206F):  # 通用标点
            count += 1
    return count
