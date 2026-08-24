"""世界观编辑器的三个工具 — 补全进度检查 / 一致性分析 / 世界圣经导出.

工具内部调用 LLM (复用 novel.llm_factory), 返回的文本作为 ToolMessage
进入对话, 供主对话 Agent 整合与展示。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from novel.llm_factory import get_llm_from_config
from world_builder.prompts import DIMENSIONS_STR

# 世界圣经导出格式 — 与 novel 图 world_agent 的输出对齐
_WORLD_BIBLE_FORMAT_PROMPT = """你是一位严谨的世界观架构师, 负责把零散的设定整理成一份结构化的"世界圣经"。

现有设定草稿如下 (可能零散/口语化, 请整合润色):
---
{world_draft}
---

题材: {genre}
故事前提: {premise}

请将上述设定组织为以下 Markdown 结构, 要求:
1. 所有内容必须来自草稿, 不要凭空新增草稿中没有的设定; 草稿缺失的维度标注"待补充"
2. 修正内部矛盾, 保持逻辑自洽
3. 用清晰的层级标题, 便于后续直接作为小说设定的唯一事实来源

输出格式 (严格遵循):
```
## 世界圣经

### 一、力量体系
(规则/等级/代价与限制)

### 二、地理格局
(地域/资源/边界)

### 三、社会结构
(政权/组织/阶级/律法)

### 四、历史脉络
(重大事件/传说/恩怨起源)

### 五、经济资源
(货币/修炼资源/稀缺性)

### 六、种族势力
(种族/阵营/关系)

### 七、需求目标
(各主要势力/人物想要什么、缺什么)

### 八、冲突网络
(矛盾/争夺/不可调和的对立)

### 九、主线看点
(根本矛盾/吸引读者的钩子)

### 十、规则边界
(什么绝不可能发生)

### 待补充清单
(草稿中缺失、需要后续章节创作中再完善的维度)
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
def check_completion(world_draft: str) -> str:
    """按 10 个世界观维度检查补全进度, 报告哪些已完整、哪些缺失。

    Args:
        world_draft: 当前累积的世界观设定草稿 (对话历史整理后的文本)

    Returns:
        各维度的完成状态报告, 供作者直观了解还缺什么。
    """
    system = (
        "你是世界观完整性的评估器。根据给定的世界观草稿, 逐维度判断其完成程度。"
        "评估维度:\n" + DIMENSIONS_STR + "\n"
        "对每个维度给出状态: ✅完整 / 🟡部分 / ❌缺失, 并附一句依据。"
        "最后给出最需要补强的 3 个维度及建议。"
    )
    prompt = f"世界观草稿:\n---\n{world_draft}\n---"
    return _invoke(prompt, system)


@tool
def analyze_consistency(world_draft: str) -> str:
    """分析世界观设定中的矛盾与漏洞, 指出需要作者澄清或修正的地方。

    Args:
        world_draft: 当前累积的世界观设定草稿

    Returns:
        矛盾点清单 + 每处的修正建议或需要作者确认的问题。
    """
    system = (
        "你是世界观一致性审查员。仔细检查给定设定中的内部矛盾、逻辑漏洞、"
        "会破坏故事可信度的设定, 按严重程度排序列出。"
        "每处给出: 矛盾描述 → 为什么是问题 → 建议的修正方向或需要作者确认的问题。"
        "如果没有明显矛盾, 明确说明并只列出潜在风险点。"
    )
    prompt = f"世界观草稿:\n---\n{world_draft}\n---"
    return _invoke(prompt, system)


@tool
def generate_world_bible(world_draft: str, genre: str, premise: str) -> str:
    """将世界观草稿整理为完整的世界圣经文档 (最终导出, 供章节生成使用)。

    Args:
        world_draft: 累积的世界观设定草稿
        genre: 小说题材 (如 都市修仙)
        premise: 故事前提 (一句话)

    Returns:
        结构化世界圣经 (## 世界圣经 格式的 Markdown 文档)。
    """
    prompt = _WORLD_BIBLE_FORMAT_PROMPT.format(
        world_draft=world_draft,
        genre=genre or "未指定",
        premise=premise or "未指定",
    )
    return _invoke(prompt, "你是严谨的世界观架构师。")


# 供图绑定使用的工具列表
WORLD_BUILDER_TOOLS = [check_completion, analyze_consistency, generate_world_bible]
