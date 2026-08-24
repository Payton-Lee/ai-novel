"""创意生成器的两个工具 — 高概念选题 / 选题市场评估."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from idea_generator.prompts import IDEA_SYSTEM_PROMPT
from novel.llm_factory import get_llm_from_config


def _invoke(prompt: str) -> str:
    llm = get_llm_from_config()
    resp = llm.invoke([
        SystemMessage(content=IDEA_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return resp.content


@tool
def generate_ideas(keywords: str) -> str:
    """根据关键词/偏好生成 3-5 个高概念选题 (含卖点与风险).

    Args:
        keywords: 作者的关键词/偏好 (如 "都市, 玄幻, 反差, 不想写修仙老套路")

    Returns:
        3-5 个结构化的高概念选题。
    """
    return _invoke(
        f"作者偏好/关键词: {keywords}\n\n请生成 3-5 个高概念选题, 风格尽量不同。"
    )


@tool
def assess_idea(idea: str) -> str:
    """评估单个选题的市场潜力与可写性.

    Args:
        idea: 一句话概念或选题描述

    Returns:
        客观评估: 差异化/吸引力/可写性/风险/是否建议开书。
    """
    return _invoke(
        f"请评估以下选题:\n{idea}\n\n"
        "从差异化、吸引力、可写性、市场风险、是否建议开书 5 个角度给出客观评估。"
    )


IDEA_TOOLS = [generate_ideas, assess_idea]
