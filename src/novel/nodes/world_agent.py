"""世界观构建 Agent — 构建和维护小说的"世界圣经"."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from typing import Optional

from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config
from novel.prompts import WORLD_SYSTEM_PROMPT
from novel.state import NovelState


def world_agent(state: NovelState, config: Optional[RunnableConfig] = None) -> dict:
    """根据世界观设定和章节大纲, 生成本章所需的世界圣经.

    输入: genre, world_setting, chapter_outline, detailed_outline
    输出: world_bible
    """
    llm = get_llm_from_config(config)

    user_prompt = f"""请根据以下信息, 构建本章的世界圣经:

## 题材
{state.get('genre', '未指定')}

## 世界观设定
{state.get('world_setting', '')}

## 章节大纲
{state.get('chapter_outline', '')}

## 细化大纲
{state.get('detailed_outline', '(尚未细化, 请根据章节大纲自行推断本章涉及的场景)')}

请按照系统提示中的格式输出世界圣经。重点突出本章会涉及的设定, 其他可以简略。"""

    resp = llm.invoke([
        SystemMessage(content=WORLD_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    return {"world_bible": resp.content}
