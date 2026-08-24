"""审稿 Agent — 严格审核章节质量并给出评分和修改意见."""

from __future__ import annotations

import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config
from novel.prompts import BANNED_PHRASES, REVIEW_SYSTEM_PROMPT
from novel.state import NovelState


def review_agent(state: NovelState, config: Optional[RunnableConfig] = None) -> dict:
    """审核当前草稿, 输出审稿报告和质量评分.

    输入: current_draft, world_bible, character_cards, detailed_outline
    输出: review_feedback, quality_score
    """
    llm = get_llm_from_config(config)

    draft = state.get("current_draft", "")

    # 先做一次自动化的禁词检测
    auto_findings = _check_banned_phrases(draft)

    auto_section = ""
    if auto_findings:
        auto_section = (
            "\n\n## 自动禁词检测结果 (以下是程序检测到的, 请确认并纳入审稿报告):\n"
            + "\n".join(f"- {f}" for f in auto_findings)
        )

    user_prompt = f"""请严格审核以下章节:

## 细化大纲 (对照标准)
{state.get('detailed_outline', '')}

## 世界圣经 (一致性对照)
{state.get('world_bible', '')}

## 人物卡片 (角色一致性对照)
{state.get('character_cards', '')}

## 待审稿件
{draft}
{auto_section}

请按照系统提示中的审稿维度和格式, 输出完整的审稿报告。
特别注意: 在报告最开头给出 "综合评分: X/10" (X 为 1-10 的整数)。"""

    resp = llm.invoke([
        SystemMessage(content=REVIEW_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    review_text = resp.content
    score = _extract_score(review_text)

    return {
        "review_feedback": review_text,
        "quality_score": score,
    }


def _check_banned_phrases(text: str) -> list[str]:
    """自动化禁词检测, 返回发现的问题列表."""
    findings: list[str] = []
    for phrase in BANNED_PHRASES:
        # 处理包含通配符的禁词 (如 "嘴角勾起一抹")
        if "…" in phrase:
            continue  # 跳过含省略号的模式
        count = text.count(phrase)
        if count > 0:
            findings.append(f'发现禁词 "{phrase}" 出现 {count} 次')
    # 检查"感到XXX"模式
    feel_pattern = re.findall(r"感到[^，。！？\n]{1,6}", text)
    for m in feel_pattern:
        findings.append(f'发现情感标签化: "{m}" (应改为身体感受描写)')
    return findings


def _extract_score(review_text: str) -> int:
    """从审稿报告中提取评分."""
    patterns = [
        r"综合评分[：:]\s*(\d{1,2})\s*/\s*10",
        r"评分[：:]\s*(\d{1,2})\s*/\s*10",
        r"(\d{1,2})\s*/\s*10\s*分",
    ]
    for p in patterns:
        m = re.search(p, review_text)
        if m:
            score = int(m.group(1))
            return max(1, min(10, score))
    return 5  # 默认中等分
