"""Chapter Contract — 章节任务单生成.

每章写作前的硬约束: 明确本章目标/必须发生/禁止透露/出场人物/伏笔推进/回收/预期状态变化/钩子。
核心价值: 让写作"有据可依", 防止长篇写崩 (OOC / 伏笔遗忘 / 提前透传)。
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config
from serial_engine.storage import StoryRepository

_CONTRACT_PROMPT = """你是连载故事的任务单规划师。根据章节大纲和当前记忆, 生成一份**章节任务单 (Chapter Contract)**, 只输出 JSON。

## 章节大纲
{chapter_outline}

## 记忆上下文 (当前故事状态)
{mem_context}

## 上章状态差异反馈 (若本章是续写, 上章有哪些预期未完成, 本章应尽力弥补)
{prev_diff}

## 输出 JSON 格式 (严格)
{{
  "title": "本章标题",
  "goals": ["本章要达成的目标, 2-4条, 必须具体"],
  "must_happen": ["必须发生的事件, 至少2条, 具体可检验"],
  "must_not_reveal": ["本章禁止透露的信息, 结合'谁知道什么'——角色不能说他不该知道的事"],
  "characters_appearing": ["出场角色名列表"],
  "plot_threads_to_advance": ["本章要推进的伏笔"],
  "plot_threads_to_resolve": ["本章要回收的伏笔(可空)"],
  "expected_character_changes": [{{"name": "角色", "from": "写前状态", "to": "写后状态"}}],
  "cliffhanger": "本章结尾钩子设计"
}}

规则:
- 全部基于大纲和记忆, 不凭空新增主线
- goals/must_happen 必须具体到可检验 (如"陈默得知母亲病源与林家有关", 而不是"剧情推进")
- must_not_reveal 要对照记忆里每个角色的"谁知道什么"——角色只知道自己该知道的信息
- expected_character_changes 的 from 应来自记忆中的当前状态
- 合法的 JSON, 不要任何解释文字"""


def generate_contract(
    repo: StoryRepository,
    story_id: str,
    chapter_no: int,
    chapter_outline: str,
    mem_context: str,
    prev_diff: str = "",
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """生成章节任务单.

    Args:
        repo: 存储库 (用于读取角色/伏笔状态)
        story_id: 故事 ID
        chapter_no: 章节号
        chapter_outline: 本章大纲
        mem_context: 组装好的分层记忆 (含谁知道什么)
        prev_diff: 上章 State Diff 反馈
        config: LangGraph config

    Returns:
        Contract dict; 失败时返回最小默认 contract。
    """
    prompt = _CONTRACT_PROMPT.format(
        chapter_outline=chapter_outline,
        mem_context=mem_context[:6000] or "(无历史记忆, 本章为开局)",
        prev_diff=prev_diff or "(无)",
    )
    try:
        llm = get_llm_from_config(config)
        resp = llm.invoke([
            SystemMessage(content="你是连载任务单规划师。只输出合法 JSON。"),
            HumanMessage(content=prompt),
        ])
        m = re.search(r"\{[\s\S]*\}", str(resp.content))
        if not m:
            return _default_contract(chapter_outline)
        data = json.loads(m.group(0))
        # 保证必填字段
        for key in ("goals", "must_happen", "must_not_reveal", "characters_appearing",
                    "plot_threads_to_advance", "plot_threads_to_resolve",
                    "expected_character_changes"):
            data.setdefault(key, [])
        data.setdefault("title", "")
        data.setdefault("cliffhanger", "")
        return data
    except Exception:
        return _default_contract(chapter_outline)


def _default_contract(chapter_outline: str) -> dict[str, Any]:
    """contract 生成失败时的兜底."""
    return {
        "title": "",
        "goals": [],
        "must_happen": [],
        "must_not_reveal": [],
        "characters_appearing": [],
        "plot_threads_to_advance": [],
        "plot_threads_to_resolve": [],
        "expected_character_changes": [],
        "cliffhanger": "",
    }


def contract_to_text(contract: dict[str, Any]) -> str:
    """把 contract 转成注入写作的约束文本."""
    if not contract:
        return ""
    lines = ["## 本章任务单 (写作硬约束, 必须全部落实)"]
    if contract.get("title"):
        lines.append(f"- 本章标题: {contract['title']}")
    if contract.get("goals"):
        lines.append("- 本章目标: " + "; ".join(contract["goals"]))
    if contract.get("must_happen"):
        lines.append("- 必须发生: " + "; ".join(contract["must_happen"]))
    if contract.get("must_not_reveal"):
        lines.append("- 禁止透露: " + "; ".join(contract["must_not_reveal"]))
    if contract.get("characters_appearing"):
        lines.append("- 出场人物: " + ", ".join(contract["characters_appearing"]))
    if contract.get("plot_threads_to_advance"):
        lines.append("- 推进伏笔: " + "; ".join(contract["plot_threads_to_advance"]))
    if contract.get("plot_threads_to_resolve"):
        lines.append("- 回收伏笔: " + "; ".join(contract["plot_threads_to_resolve"]))
    if contract.get("expected_character_changes"):
        changes = "; ".join(
            f"{c.get('name','?')}: {c.get('from','?')} → {c.get('to','?')}"
            for c in contract["expected_character_changes"]
        )
        lines.append(f"- 预期状态变化: {changes}")
    if contract.get("cliffhanger"):
        lines.append(f"- 结尾钩子: {contract['cliffhanger']}")
    if contract.get("target_words"):
        lines.append(f"- 本章目标字数: {contract['target_words']} 字 (写完后必须校验, 超范围需调整)")
    return "\n".join(lines)
