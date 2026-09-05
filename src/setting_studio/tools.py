"""设定工作台工具 — 纯生成 (LLM), 落库由 graph 的 tools_node 处理.

每个工具接收当前设定板块内容, 产出目标文档/图; 避免工具持有 project_id/副作用。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from novel.llm_factory import get_llm_from_config


def _invoke(prompt: str, system: str) -> str:
    llm = get_llm_from_config()
    resp = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ])
    return str(resp.content).strip()


# ============================================================
# 1. 记录设定 (增量合并进板块)
# ============================================================

@tool
def record_setting(section: str, content: str) -> str:
    """把作者给的设定内容写入指定板块 (world/characters/relationships/timeline/conflicts/outline).

    Args:
        section: 目标板块
        content: 该板块完整/更新后的设定文本 (作者对话 + 已有设定整合)

    Returns:
        确认提示 (实际写入由系统处理)。
    """
    return f"[已整理 {section} 板块设定, 待写入]"

# ============================================================
# 2. 时间线生成
# ============================================================

_TIMELINE_PROMPT = """你是时间线架构师。根据世界观历史、人物成长和大纲, 生成一条**符合逻辑因果**的小说时间线。

## 世界观
{world}

## 人物成长 (含起点/转折/终点)
{characters}

## 大纲事件
{outline}

## 要求
1. 把"世界线大事件 / 人物成长关键点 / 剧情节点"融合成一条连贯时间线
2. **因果逻辑**: 每个事件须能由前事推导 (标注关键因果链, 如 "← 因X")
3. 按时间先后排序, 标注时间点 (如"开篇·三年前 / 卷一·第X章")
4. 每条含: 时间点 | 事件 | 关联角色 | 类型(世界/成长/剧情)
5. 只做整合, 不凭空新增主线; 冲突处标注需作者定夺

输出格式 (Markdown):
```
## 时间线
### 前史 (开篇前)
- [时间] 事件 (角色) [类型] ← 因果说明
### 卷一
...
```
"""


@tool
def generate_timeline(world: str, characters: str, outline: str) -> str:
    """从世界观+人物成长+大纲生成逻辑自洽的时间线.

    Args:
        world: 世界观设定
        characters: 人物设定 (含成长弧)
        outline: 大纲

    Returns:
        结构化时间线 markdown。
    """
    return _invoke(
        _TIMELINE_PROMPT.format(
            world=world or "(空)", characters=characters or "(空)", outline=outline or "(空)"
        ),
        "你是时间线架构师, 保证事件因果连贯。",
    )


# ============================================================
# 3. 人物描写小卡
# ============================================================

_CARD_PROMPT = """你是人物造型师。为角色生成一张**写作向描写小卡**, 让写手一看到就知道怎么把这个角色写"活"。

## 角色设定
{character}

## 已有角色库 (避免与其他角色描写雷同)
{characters}

输出格式:
```
### [角色名] — [人设标签]  ← 如: 冰山美人·外冷内热 / 笑面虎·皮笑肉不笑
- 核心印象: (一句话, 读者第一眼记住什么)
- 描写方向:
  - 神态: (专属表情/眼神, 别泛泛"冷冷地说")
  - 动作习惯: (坐下/走路/手部小动作)
  - 语言特征: (句式/口头禅/语速)
  - 专属标志动作 (3个): (只有这个角色会做的, 如"拨弄袖口银链")
- 情绪外化方式: (生气/紧张/开心时身体怎么反应, 禁止写"他很生气")
- 禁忌描写: (这个角色绝不那样写, 防串味)
- 开场白建议: (第一句台词/出场动作, 立住人设)
```
要求: 标签用"形容词+反差"给读者直觉; 每个描写点要给**可执行的画面**而非形容词堆叠。"""


@tool
def generate_character_card(character: str, characters: str) -> str:
    """为单个角色生成描写小卡 (人设标签/描写方向/情绪外化/禁忌).

    Args:
        character: 该角色的设定 (姓名/性格/外貌/背景)
        characters: 已有角色库 (避免描写雷同)

    Returns:
        该角色的写作向描写小卡。
    """
    return _invoke(
        _CARD_PROMPT.format(character=character, characters=characters or "(尚无其他角色)"),
        "你是人物造型师, 产出可执行的描写小卡。",
    )


# ============================================================
# 4. 冲突推演
# ============================================================

_CONFLICT_PROMPT = """你是冲突推演师。从「人物欲望 × 性格 × 世界规则」系统性地推演这部小说**可能发生的冲突**, 供作者选用或触发。

## 世界观 (规则/势力)
{world}

## 人物 (含欲望/性格/关系)
{characters}

## 已有关系
{relationships}

## 推演要求
- 对每个主要人物, 从其欲望出发: 欲望 vs 谁/什么会成为障碍 (另一人物 / 世界规则 / 自身)
- 给 4-8 个候选冲突, 覆盖: 人际冲突 / 与世界规则冲突 / 内心冲突 / 势力冲突
- 每个冲突标注张力来源 (欲望在哪儿撞上了) 和不可调和性 (为什么不能轻易解决)
- 冲突要能支撑剧情推进 (不是背景设定, 是有戏可写的)

输出格式:
```
### 候选冲突 N: [一句话]
- 双方: A vs B (或 A vs 世界/自身)
- 触发点: (什么场景会引爆)
- 张力来源: (A 的欲望 X 撞上 B 的欲望/规则 Y)
- 不可调和性: ...
- 可演化走向: (如何升级/转化)
- 适配章节: (建议放哪段剧情)
```
"""


@tool
def deduce_conflicts(world: str, characters: str, relationships: str) -> str:
    """从欲望×性格×世界规则推演候选冲突.

    Args:
        world: 世界观 (规则/势力)
        characters: 人物 (欲望/性格/关系)
        relationships: 人物关系

    Returns:
        4-8 个候选冲突。
    """
    return _invoke(
        _CONFLICT_PROMPT.format(
            world=world or "(空)", characters=characters or "(空)", relationships=relationships or "(空)"
        ),
        "你是冲突推演师, 从欲望与规则推演有戏可写的冲突。",
    )


# ============================================================
# 5. 关系图 (Mermaid 生成)
# ============================================================

_RELATION_PROMPT = """你是关系图设计师。根据人物设定和关系, 生成 Mermaid 人物关系图。

## 人物
{characters}

## 关系
{relationships}

要求:
1. `graph LR`, 每个主要人物一节点: `名字["名字<br/>定位"]`
2. 边类型: `-->`实线(明确关系) / `-.->`虚线(暗线/猜疑) / `==>`粗线(生死对立)
3. 每条边带标签: `陈默 ==>|生死仇敌| 大长老`
4. 只从设定中提取, 不虚构

只输出 ```mermaid ``` 代码块, 不要解释。"""


@tool
def build_relationship_graph(characters: str, relationships: str) -> str:
    """生成人物关系图 (Mermaid 代码).

    Args:
        characters: 人物设定
        relationships: 关系描述

    Returns:
        Mermaid 代码 (graph LR)。
    """
    return _invoke(
        _RELATION_PROMPT.format(characters=characters or "(空)", relationships=relationships or "(空)"),
        "你是关系图设计师。",
    )


# ============================================================
# 6. 导出完整设定文档
# ============================================================

@tool
def export_doc(
    world: str, characters: str, relationships: str,
    timeline: str, conflicts: str, outline: str,
) -> str:
    """把全部板块整合成一份完整设定文档 (Markdown).

    Args:
        world/characters/relationships/timeline/conflicts/outline: 各板块内容

    Returns:
        完整设定文档 (供导出到文件)。
    """
    parts = [
        "# 完整设定文档", "",
        "## 世界观", world or "(未设定)", "",
        "## 人物", characters or "(未设定)", "",
        "## 人物关系", relationships or "(未设定)", "",
        "## 时间线", timeline or "(未生成)", "",
        "## 冲突推演", conflicts or "(未推演)", "",
        "## 大纲", outline or "(未规划)", "",
    ]
    return "\n".join(parts)


SETTING_STUDIO_TOOLS = [
    record_setting,
    generate_timeline,
    generate_character_card,
    deduce_conflicts,
    build_relationship_graph,
    export_doc,
]
