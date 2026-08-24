"""读者模拟器的两个工具 — 读者视角评估 / 修改建议."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from novel.llm_factory import get_llm_from_config
from reader_simulator.prompts import READER_SYSTEM_PROMPT


def _invoke(prompt: str, system: str) -> str:
    llm = get_llm_from_config()
    resp = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ])
    return resp.content


@tool
def assess_chapter(text: str, genre: str, audience: str) -> str:
    """从目标读者视角评估章节: 黄金三章/爽点密度/追读测试/弃书风险。

    Args:
        text: 待评估的章节文本 (可多章)
        genre: 题材
        audience: 目标读者画像 (如 "追爽文男频, 追读率高")

    Returns:
        读者视角评估报告: 追读率预测 + 各维度评分 + 最致命问题。
    """
    system = (
        READER_SYSTEM_PROMPT
        + f"\n\n目标读者画像: {audience or '未指定(默认追爽文读者)'}\n题材: {genre or '未指定'}"
    )
    prompt = f"请以读者视角评估以下章节:\n\n---\n{text[:8000]}\n---"
    return _invoke(prompt, system)


@tool
def suggest_improvements(text: str) -> str:
    """从读者角度给出具体修改建议: 优先改哪、怎么改。

    Args:
        text: 待修改的章节文本

    Returns:
        按优先级排序的修改清单 (每项: 问题 → 为什么 → 怎么改 → 改后预期)。
    """
    system = (
        "你是网文读者的化身, 同时是资深内容编辑。针对章节给**具体可执行的修改建议**, "
        "不要泛泛而谈。每项包含: 读者会怎么反应 → 问题在哪 → 具体怎么改 → 改后读者感受。"
        "按优先级排序, 最多给 5 条。"
    )
    prompt = f"请针对以下章节给出修改建议:\n\n---\n{text[:8000]}\n---"
    return _invoke(prompt, system)


READER_TOOLS = [assess_chapter, suggest_improvements]
