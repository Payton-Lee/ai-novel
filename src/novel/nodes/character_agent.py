"""人物设定 Agent — 为每个角色建立独特的人物卡片."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from typing import Optional

from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config
from novel.prompts import CHARACTER_SYSTEM_PROMPT
from novel.state import NovelState


def character_agent(state: NovelState, config: Optional[RunnableConfig] = None) -> dict:
    """根据角色基础设定和章节大纲, 生成详细的人物卡片.

    输入: genre, characters, chapter_outline, detailed_outline
    输出: character_cards
    """
    llm = get_llm_from_config(config)

    chars = state.get("characters", [])
    char_list = "\n\n".join(
        f"### {c.get('name', '未知')}\n"
        f"- 角色: {c.get('role', '配角')}\n"
        f"- 性格: {c.get('personality', '待补充')}\n"
        f"- 背景: {c.get('background', '待补充')}"
        for c in chars
    )

    user_prompt = f"""请根据以下信息, 为本章出场的角色生成详细的人物卡片:

## 题材
{state.get('genre', '未指定')}

## 角色基础设定
{char_list}

## 章节大纲
{state.get('chapter_outline', '')}

## 细化大纲
{state.get('detailed_outline', '(尚未细化, 请根据章节大纲推断角色在本章中的表现)')}

请按照系统提示中的格式, 为每个角色生成一张人物卡片。重点设计语言风格和本章的情感弧线。"""

    resp = llm.invoke([
        SystemMessage(content=CHARACTER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    return {"character_cards": resp.content}
