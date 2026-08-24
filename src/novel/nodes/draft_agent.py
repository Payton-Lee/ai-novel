"""初稿生成 Agent — 将大纲转化为引人入胜的章节正文."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from typing import Optional

from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config
from novel.prompts import DRAFT_SYSTEM_PROMPT
from novel.state import NovelState


def draft_agent(state: NovelState, config: Optional[RunnableConfig] = None) -> dict:
    """根据大纲、世界圣经、人物卡片生成章节初稿.

    输入: detailed_outline, world_bible, character_cards, style_guide,
          prev_chapter_summary, review_feedback (重写时), iteration_count
    输出: current_draft, iteration_count+1
    """
    llm = get_llm_from_config(config)

    iteration = state.get("iteration_count", 0)

    # 构建上下文
    context_parts = []

    context_parts.append(f"## 细化大纲\n{state.get('detailed_outline', '')}")
    context_parts.append(f"## 世界圣经\n{state.get('world_bible', '')}")
    context_parts.append(f"## 人物卡片\n{state.get('character_cards', '')}")

    if state.get("style_guide"):
        context_parts.append(f"## 用户风格要求\n{state['style_guide']}")

    if state.get("prev_chapter_summary"):
        context_parts.append(f"## 前情摘要\n{state['prev_chapter_summary']}")

    # 如果是重写, 加入审稿意见
    if iteration > 0 and state.get("review_feedback"):
        context_parts.append(
            f"## 审稿意见 (必须逐条修改)\n{state['review_feedback']}"
        )
        context_parts.append(
            f"\n⚠️ 这是第 {iteration + 1} 次重写, 请务必解决上述所有问题。"
        )

    user_prompt = "\n\n".join(context_parts) + "\n\n请开始写作, 直接输出正文:"

    resp = llm.invoke([
        SystemMessage(content=DRAFT_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    return {
        "current_draft": resp.content,
        "iteration_count": iteration + 1,
    }
