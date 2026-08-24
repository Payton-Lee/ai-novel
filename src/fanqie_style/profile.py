"""用户样本风格提取 — 从作者认可的番茄样本文本中提炼风格特征."""

from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config

_PROFILE_PROMPT = """你是一位文风分析专家。以下是作者认可的**番茄小说风格样本文本** (2-3 段, 可能是同一作品或不同作品)。

请提炼出可复制的**风格特征清单**, 用于指导 AI 写作原创内容。从以下维度分析:
1. 句式: 长短句比例、是否碎片句、断句习惯
2. 段落: 每段多长、段与段衔接方式
3. 对话: 占比、对白风格(是否口语/带语气词/互相抢话)、对话如何推进
4. 情绪表达: 直给还是含蓄、情绪如何外化
5. 打脸/爽点写法: 反转怎么安排、观众反应怎么写
6. 叙事视角与节奏: 视角、信息释放速度、钩子怎么埋
7. 语言习惯: 口语词、网络用语、禁用的书面腔
8. 标点与排版: 是否爱用短句分行、感叹号/省略号频率

输出格式 (Markdown 清单, 每条要具体可执行):
```
### 风格特征清单
1. **句式**: ...
2. **段落**: ...
...
```

要求:
- 只描述"怎么写", 不要复述样本情节
- 每条特征要能直接指导写作 (如"爱用'……'表示停顿"而不是"文笔生动")
- 若样本间风格冲突, 注明"以主要样本为准"
- 尊重版权: 提炼的是风格模式, 不是原文句子"""


def extract_style_profile(
    user_samples: str,
    config: Optional[RunnableConfig] = None,
) -> str:
    """从用户粘贴的样本文本提取风格特征.

    Args:
        user_samples: 用户认可的番茄风格样本文本 (2-3 段)
        config: LangGraph config

    Returns:
        风格特征清单 (Markdown); 样本过短/失败时返回空字符串。
    """
    samples = user_samples.strip()
    if not samples or len(samples) < 100:
        return ""

    # 截断避免超长
    samples = samples[:6000]
    try:
        llm = get_llm_from_config(config)
        resp = llm.invoke([
            SystemMessage(content="你是文风分析专家。提炼可复制的写作风格特征, 不要复述情节。"),
            HumanMessage(content=_PROFILE_PROMPT + "\n\n## 样本文本\n" + samples),
        ])
        text = str(resp.content).strip()
        return text if len(text) > 50 else ""
    except Exception:
        return ""


def compact_profile(profile: str, max_len: int = 1500) -> str:
    """压缩风格画像, 控制注入 token."""
    if not profile:
        return ""
    if len(profile) <= max_len:
        return profile
    # 保留开头特征清单, 截断尾部
    return profile[:max_len] + "\n...(截断)"
