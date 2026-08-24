"""人物定义器的四个工具 — 完成度检查 / 一致性分析 / 人物卡片导出 / 关系图生成.

工具内部调用 LLM (复用 novel.llm_factory), 返回文本作为 ToolMessage
进入对话, 供主对话 Agent 整合展示。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from character_builder.prompts import (
    ABILITY_TREE_FORMAT,
    APPEARANCE_FORMAT,
    DIMENSIONS_STR,
    RELATIONSHIP_FORMAT,
)
from character_builder.render import render_relationship_html
from novel.llm_factory import get_llm_from_config

# 人物卡片导出格式 — 对齐 novel 图 CharacterCard (name/role/personality/background/speech_style)
_CARDS_FORMAT_PROMPT = """你是一位严谨的人物造型师。请把对话中确定的人物设定, 整理成一份**结构化人物卡片集**。

## 设定草稿
---
{char_draft}
---

## 题材
{genre}

## 故事前提
{premise}

## 世界观 (背景)
{world_bible}

请为每个角色生成一张卡片, 严格遵循以下格式 (每个字段必填, 草稿缺失处标注"待补充", 不要编造):

```
### [角色名] — [角色定位]
- role: [主角/女主/反派/配角]           ← novel 图需要的字段
- personality: [性格内核, 含矛盾点]
- background: [背景经历, 2-4句]
- speech_style: [语言风格: 口头禅/句式/禁忌说话方式]
- 外貌特征:
{APPEARANCE_FORMAT}
- 目标与欲望: ...
- 弱点与恐惧: ...
- 成长弧线: 起点 → 转变 → 终点
- 能力树:
{ABILITY_TREE_FORMAT}
- 关系网络:
{RELATIONSHIP_FORMAT}
- 本章状态(current_status): 初始状态
```

注意:
1. 每张卡片的 name/role/personality/background/speech_style 必须字段名精确,
   供 novel 图直接读取。
2. 保持语言风格差异: 每个角色的口头禅不能与其他角色雷同。
3. 外貌特征必须按静态轮廓/动态神态/服饰风格三子维度填写。
4. 关系网络每段关系必须含: 关系类型/张力点/关系历史/关系走向 四要素。
"""

# 关系图生成提示词
_RELATIONSHIP_PROMPT = """你是人物关系图设计师。根据人物设定草稿, 生成一张 **Mermaid 人物关系图**。

## 设定草稿
---
{char_draft}
---

要求:
1. 用 `graph LR` 方向 (横向布局, 人物多时优先清晰)。
2. 每个主要人物一个节点, 节点格式: `角色名["角色名<br/>角色定位"]` (如 `陈默["陈默<br/>主角"]`)。
3. 用不同边类型表达关系性质:
   - `-->` 实线: 明确关系 (结盟/恋人/师徒/上下级)
   - `-.->` 虚线: 暗线/潜在 (暗中调查/怀疑/秘密)
   - `==>` 粗线: 强烈对立/生死仇敌
   - 每条边加关系标签: `陈默 ==>|生死仇敌| 大长老`
4. 关系必须从草稿中提取, 不要凭空捏造角色或关系。
5. 如果存在且角色相关, 可加入"凡人亲属"这类人物节点。

只输出 Mermaid 代码块, 不要任何解释文字。代码块格式:
```mermaid
graph LR
...
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


@tool
def check_character_completion(char_draft: str) -> str:
    """按人物维度清单检查各角色的完成度, 报告哪些已完整、哪些缺失。

    Args:
        char_draft: 当前累积的人物设定草稿

    Returns:
        各角色/各维度的完成状态报告。
    """
    system = (
        "你是人物设定的完整性评估器。根据给定的人物草稿, 逐维度判断完成程度。\n"
        "人物维度:\n" + DIMENSIONS_STR + "\n"
        "先列出草稿中出现的所有角色, 再逐个角色判断哪些维度完整(✅)/部分(🟡)/缺失(❌)。"
        "最后给出最需要补强的 3 处及建议。"
    )
    prompt = f"人物设定草稿:\n---\n{char_draft}\n---"
    return _invoke(prompt, system)


@tool
def analyze_character_consistency(char_draft: str) -> str:
    """分析人物设定中的问题: 矛盾、能力失衡、弧线缺失、关系网断裂。

    Args:
        char_draft: 当前累积的人物设定草稿

    Returns:
        按严重程度排序的问题清单 + 修正建议。
    """
    system = (
        "你是人物设定的结构审查员。检查给定人物设定中的: "
        "性格前后矛盾、能力过强或过弱(是否无解/无代价)、成长弧线缺失、"
        "与其他角色的关系是否单向断裂、语言风格是否区分度不足、"
        "设定是否与世界观/大纲冲突。按严重程度排序列出。"
        "每处给出: 问题描述 → 为什么是问题 → 修正建议。"
    )
    prompt = f"人物设定草稿:\n---\n{char_draft}\n---"
    return _invoke(prompt, system)


@tool
def generate_character_cards(char_draft: str, genre: str, premise: str, world_bible: str) -> str:
    """将人物设定整理为结构化人物卡片集 (最终导出, 供章节生成逐章使用)。

    Args:
        char_draft: 累积的人物设定草稿
        genre: 小说题材
        premise: 故事前提
        world_bible: 世界观圣经 (背景)

    Returns:
        结构化人物卡片集; 每张卡片含 novel 图所需的 name/role/personality/background/speech_style 字段。
    """
    prompt = _CARDS_FORMAT_PROMPT.format(
        char_draft=char_draft,
        genre=genre or "未指定",
        premise=premise or "未指定",
        world_bible=world_bible or "(未提供)",
        ABILITY_TREE_FORMAT=ABILITY_TREE_FORMAT,
        APPEARANCE_FORMAT=APPEARANCE_FORMAT,
        RELATIONSHIP_FORMAT=RELATIONSHIP_FORMAT,
    )
    return _invoke(prompt, "你是严谨的人物造型师。")


@tool
def generate_relationship_graph(char_draft: str) -> str:
    """生成人物关系图: 返回 Mermaid 代码, 同时渲染为 HTML 文件。

    Args:
        char_draft: 累积的人物设定草稿

    Returns:
        提示信息, 包含 Mermaid 关系图代码块和 HTML 文件路径。
    """
    mermaid_code = _invoke(
        _RELATIONSHIP_PROMPT.format(char_draft=char_draft),
        "你是人物关系图设计师。",
    )

    html_path = render_relationship_html(mermaid_code, title="人物关系图")
    path_note = f"\n\n📄 HTML 关系图已生成: `{html_path}`\n(双击该文件, 浏览器中即可查看可交互的关系图。)" if html_path else "\n\n(HTML 渲染失败, 请使用上面的 Mermaid 代码)"

    return mermaid_code + path_note


# 供图绑定使用的工具列表
CHARACTER_BUILDER_TOOLS = [
    check_character_completion,
    analyze_character_consistency,
    generate_character_cards,
    generate_relationship_graph,
]
