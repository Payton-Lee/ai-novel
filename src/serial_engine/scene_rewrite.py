"""场景级重写 — reader FAIL 时只重写问题场景, 替代整章重写.

流程: split_scenes(切场景块) → locate_problem_scenes(LLM 定位问题块)
    → rewrite_scenes(LLM 重写问题块, 其余保持原样).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from novel.llm_factory import get_llm_from_config

# 每个场景块约 400 字, 保证定位粒度合理
SCENE_TARGET_CHARS = 400


def split_scenes(chapter_text: str) -> list[str]:
    """把章节按段落切分为场景块 (约 SCENE_TARGET_CHARS 字一块).

    Args:
        chapter_text: 章节全文

    Returns:
        场景块列表 (每块是若干段落拼接)。
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter_text) if p.strip()]
    if not paragraphs:
        return [chapter_text]

    scenes: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for p in paragraphs:
        buf.append(p)
        buf_len += len(p)
        if buf_len >= SCENE_TARGET_CHARS:
            scenes.append("\n\n".join(buf))
            buf = []
            buf_len = 0
    if buf:
        scenes.append("\n\n".join(buf))
    return scenes


def _number_scenes(scenes: list[str]) -> str:
    """给场景块加编号, 供 LLM 定位."""
    return "\n\n".join(f"[场景{i}] {s}" for i, s in enumerate(scenes))


_LOCATE_PROMPT = """你是场景定位器。给定章节(已按场景分块, 每块标了 [场景N]) 和读者反馈, 判断**哪些场景块是问题的根源**, 只输出有问题的场景编号。

读者反馈:
{feedback}

章节(分块):
{numbered_scenes}

规则:
- 只标出直接导致读者反馈问题的场景块 (如节奏拖沓的开头、没爽点的段落、OOC的对话)
- 数量宁少勿多, 只标 1-3 块; 没问题标 []
- 只输出 JSON: {{"problem_scenes": [0, 2]}}
- 编号必须来自上面的 [场景N], 用 N (从0开始)"""


def locate_problem_scenes(
    chapter_text: str,
    reader_feedback: str,
    config: Optional[RunnableConfig] = None,
) -> list[int]:
    """用 LLM 定位问题场景块.

    Args:
        chapter_text: 章节全文
        reader_feedback: reader 反馈
        config: LangGraph config

    Returns:
        问题场景块编号列表; 失败返回 []。
    """
    scenes = split_scenes(chapter_text)
    if len(scenes) <= 1:
        return []
    prompt = _LOCATE_PROMPT.format(
        feedback=reader_feedback[:2000] or "(无)",
        numbered_scenes=_number_scenes(scenes)[:8000],
    )
    try:
        llm = get_llm_from_config(config)
        resp = llm.invoke([
            SystemMessage(content="你是场景定位器。只输出合法 JSON。"),
            HumanMessage(content=prompt),
        ])
        m = re.search(r"\{[\s\S]*\}", str(resp.content))
        if not m:
            return []
        data = m.group(0)
        import json
        parsed = json.loads(data)
        ids = parsed.get("problem_scenes", [])
        return [i for i in ids if isinstance(i, int) and 0 <= i < len(scenes)]
    except Exception:
        return []


_REWRITE_PROMPT = """你是章节修改师。根据读者反馈, 重写章节中**指定场景块**, 其他场景块**原样保留**。

读者反馈 (要解决的问题):
{feedback}

需重写的场景块编号:
{scene_ids}

章节全文:
{full_text}

要求:
1. 只修改指定编号的场景块内容, 其他部分一字不改
2. 保持整章的行文风格、人物语言习惯一致
3. 不新增人物/剧情, 只改进节奏/爽点/钩子/对话等读者反馈的问题
4. 输出重写后的**完整章节** (含所有未改动场景), 不要解释
5. 单章字数保持 2000-2200 字"""


def rewrite_scenes(
    chapter_text: str,
    scene_ids: list[int],
    reader_feedback: str,
    config: Optional[RunnableConfig] = None,
) -> str:
    """重写指定场景块, 返回重写后的完整章节.

    Args:
        chapter_text: 原章节
        scene_ids: 要重写的场景块编号
        reader_feedback: reader 反馈
        config: LangGraph config

    Returns:
        重写后的完整章节; 失败返回原章节。
    """
    if not scene_ids:
        return chapter_text
    prompt = _REWRITE_PROMPT.format(
        feedback=reader_feedback[:2000] or "(无)",
        scene_ids=", ".join(str(i) for i in scene_ids),
        full_text=chapter_text,
    )
    try:
        llm = get_llm_from_config(config)
        resp = llm.invoke([
            SystemMessage(content="你是章节修改师。保持其他场景原样, 只改指定场景。"),
            HumanMessage(content=prompt),
        ])
        new_text = str(resp.content).strip()
        return new_text if len(new_text) > 500 else chapter_text
    except Exception:
        return chapter_text
