"""大纲规划器的三个工具 — 完成度检查 / 结构一致性分析 / 完整大纲导出.

工具内部调用 LLM (复用 novel.llm_factory), 返回文本作为 ToolMessage
进入对话, 供主对话 Agent 整合展示。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from novel.llm_factory import get_llm_from_config
from outline_planner.prompts import OUTLINE_STRUCTURE

# 完整大纲导出格式
_FULL_OUTLINE_FORMAT_PROMPT = """你是一位资深网络小说大纲规划师, 负责把对话中确定的大纲草稿, 整理成一份完整、可执行、分卷分章的《全书大纲》。

## 草稿
---
{outline_draft}
---

## 题材
{genre}

## 故事前提
{premise}

## 世界观圣经
{world_bible}

## 人物
{characters}

请将以上信息组织为下面的 Markdown 结构:
- 所有事件、冲突、伏笔必须来自草稿与素材, 不要凭空新增草稿中没有的情节
- 明确标注每一卷的"卷末大钩子"和每一章的"章末钩子"
- 标注每章埋设/回收的伏笔
- 若草稿缺失某部分, 在"待补充清单"中列出, 不要自行编造

输出格式 (严格遵循):
```
## 全书大纲

### 核心主线
- 一句话主线:
- 主角成长弧线:
- 结局指向:

### 分卷规划
**第X卷 [卷名]**
- 卷主题/目标:
- 起承转合: 起: ... 承: ... 转: ... 合: ...
- 卷末大钩子:

### 分章大纲
**第X章 [标题]**
- 核心事件:
- 冲突:
- 章末钩子:
- 涉及人物:
- 伏笔: 埋设/回收

### 待补充清单
(缺失、待作者后续确定的元素)
```
"""


def _invoke(prompt: str, system: str) -> str:
    """调用默认配置的 LLM 生成文本."""
    llm = get_llm_from_config()
    resp = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ])
    return resp.content


def _characters_str(characters: Any) -> str:
    """把人物列表格式化为可读文本."""
    if not characters:
        return "(未提供)"
    if isinstance(characters, str):
        return characters
    try:
        lines = []
        for c in characters:
            if isinstance(c, dict):
                lines.append(
                    f"- {c.get('name', '?')} ({c.get('role', '配角')}): "
                    f"{c.get('personality', '')}"
                )
            else:
                lines.append(f"- {c}")
        return "\n".join(lines)
    except Exception:
        return json.dumps(characters, ensure_ascii=False, default=str)


@tool
def check_outline_completion(outline_draft: str) -> str:
    """按大纲结构维度检查完成度, 报告哪些已完整、哪些缺失。

    Args:
        outline_draft: 当前累积的大纲草稿

    Returns:
        各结构维度的完成状态报告, 供作者直观了解还缺什么。
    """
    system = (
        "你是大纲完整性的评估器。根据给定的大纲草稿, 逐维度判断完成程度。\n"
        "结构维度:\n" + OUTLINE_STRUCTURE + "\n"
        "对每个维度给出状态: ✅完整 / 🟡部分 / ❌缺失, 并附一句依据。"
        "最后给出最需要补强的 3 个维度及建议。"
    )
    prompt = f"大纲草稿:\n---\n{outline_draft}\n---"
    return _invoke(prompt, system)


@tool
def analyze_plot_consistency(outline_draft: str) -> str:
    """分析大纲中的结构问题: 主线断裂、伏笔丢失、节奏拖沓、逻辑矛盾。

    Args:
        outline_draft: 当前累积的大纲草稿

    Returns:
        按严重程度排序的结构问题清单 + 修正建议。
    """
    system = (
        "你是小说大纲的结构审查员。仔细检查给定大纲中的: "
        "主线是否断裂、伏笔是否埋了没收、节奏是否拖沓或跳跃、卷章衔接是否顺畅、"
        "人物动机是否前后一致。按严重程度排序列出。"
        "每处给出: 问题描述 → 为什么是问题 → 修正建议。"
        "如果没有明显问题, 明确说明并只列潜在风险。"
    )
    prompt = f"大纲草稿:\n---\n{outline_draft}\n---"
    return _invoke(prompt, system)


@tool
def generate_full_outline(
    outline_draft: str,
    genre: str,
    premise: str,
    world_bible: str,
    characters: Any,
) -> str:
    """将大纲草稿整理为完整的分卷分章《全书大纲》(最终导出, 供章节生成逐章使用)。

    Args:
        outline_draft: 累积的大纲草稿
        genre: 小说题材
        premise: 故事前提
        world_bible: 世界观圣经 (来自世界观编辑器)
        characters: 人物列表

    Returns:
        结构化《全书大纲》文档 (## 全书大纲 格式)。
    """
    prompt = _FULL_OUTLINE_FORMAT_PROMPT.format(
        outline_draft=outline_draft,
        genre=genre or "未指定",
        premise=premise or "未指定",
        world_bible=world_bible or "(未提供)",
        characters=_characters_str(characters),
    )
    return _invoke(prompt, "你是资深网络小说大纲规划师。")


# 供图绑定使用的工具列表
OUTLINE_PLANNER_TOOLS = [check_outline_completion, analyze_plot_consistency, generate_full_outline]
