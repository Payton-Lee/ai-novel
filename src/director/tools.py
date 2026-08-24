"""创作导演的六个阶段工具 — 调度现有 Agent 的导出逻辑.

每个工具内部调用对应 Agent 的生成工具 (复用, 不重新实现),
产出可用的初版文档, 由导演向作者汇报。
"""

from __future__ import annotations

import re
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
    return str(resp.content)


# ============================================================
# ① 创意
# ============================================================

@tool
def generate_idea(goal: str, style: str) -> str:
    """生成高概念选题 (题材+核心矛盾+卖点+目标读者).

    Args:
        goal: 作者的创作目标/偏好
        style: 目标平台或风格 (如 "番茄小说")

    Returns:
        3-5 个高概念选题。
    """
    from idea_generator.tools import generate_ideas
    return generate_ideas.invoke({"keywords": f"{goal} | 目标平台: {style or '番茄小说'}"})


# ============================================================
# ② 世界观
# ============================================================

@tool
def build_world(idea: str, genre: str) -> str:
    """从选题生成世界圣经.

    Args:
        idea: 一句话概念/选题
        genre: 题材

    Returns:
        结构化世界圣经 (## 世界圣经 格式)。
    """
    from world_builder.tools import generate_world_bible
    # 用选题作为草稿起点, 让 LLM 扩展为完整世界观
    return generate_world_bible.invoke({
        "world_draft": f"核心创意: {idea}\n题材: {genre}",
        "genre": genre,
        "premise": idea,
    })


# ============================================================
# ③ 人物
# ============================================================

@tool
def build_characters(idea: str, world: str, genre: str) -> str:
    """从选题和世界观生成人物卡片集.

    Args:
        idea: 一句话概念
        world: 世界圣经
        genre: 题材

    Returns:
        结构化人物卡片集 (含 novel 图字段)。
    """
    from character_builder.tools import generate_character_cards
    return generate_character_cards.invoke({
        "char_draft": f"故事: {idea}\n出场人物: 主角(由世界观推导)、女主/关键配角、反派(对应世界观冲突)",
        "genre": genre,
        "premise": idea,
        "world_bible": world,
    })


# ============================================================
# ④ 大纲
# ============================================================

@tool
def plan_outline(idea: str, world: str, characters: str, genre: str) -> str:
    """生成分卷分章完整大纲.

    Args:
        idea: 一句话概念
        world: 世界圣经
        characters: 人物卡片
        genre: 题材

    Returns:
        《全书大纲》(## 全书大纲 格式)。
    """
    from outline_planner.tools import generate_full_outline
    return generate_full_outline.invoke({
        "outline_draft": f"核心创意: {idea}\n已确定世界观与人物, 请规划完整分卷分章大纲(含每章钩子与伏笔)",
        "genre": genre,
        "premise": idea,
        "world_bible": world,
        "characters": characters,
    })


# ============================================================
# ⑤ 连载准备
# ============================================================

_OUTLINE_GEN = """你是连载大纲生成器。为一部小说生成前 {n} 章简短章节大纲, 每章一句话(不超过60字), 连续推进主线, 章章有进展有钩子。

题材: {genre}
前提: {idea}

番茄风格要求: 前3章开篇即炸(打脸+身份反转), 每3章一个爽点, 章末留钩子。

输出格式: 每行 "第X章: 内容"。不要解释。"""


@tool
def prepare_serial(
    story_id: str,
    idea: str,
    world: str,
    characters: str,
    genre: str,
    chapters: int,
    word_targets: str,
) -> str:
    """准备连载输入: 生成 N 章大纲 + 解析每章字数目标, 返回启动说明.

    Args:
        story_id: 连载故事 ID (自行指定, 如 "mybook1")
        idea: 故事前提
        world: 世界圣经
        characters: 人物卡片
        genre: 题材
        chapters: 首批连载章数
        word_targets: 作者确认的每章字数配置, 如 "前3章2000-2200, 第4章6000-7000, 第5-6章3000-4000"
                     或全局 "2000-2200"; 留空用默认番茄 2000-2200

    Returns:
        连载准备提示 (story_id + 大纲 + chapter_targets + 如何在 serial_engine 启动)。
    """
    n = max(1, min(chapters, 50))
    outlines = _generate_outlines(idea, genre, n)
    targets = _parse_word_targets(word_targets, n)
    outline_list = "\n".join(f"{i+1}. {o}" for i, o in enumerate(outlines))
    target_list = "\n".join(
        f"  第{i+1}章: {t['min_words']}-{t['max_words']}字" for i, t in enumerate(targets)
    )

    return (
        f"连载已准备就绪。\n"
        f"- **story_id**: `{story_id}`\n"
        f"- **题材**: {genre}\n"
        f"- **首批 {n} 章大纲**:\n{outline_list}\n\n"
        f"- **每章字数目标** (已确认):\n{target_list}\n\n"
        f"启动方式: 在 serial_engine 图运行, 输入 story_id=`{story_id}` + mode=`continuous` + "
        f"上述章节大纲列表 + chapter_targets(见上) + 世界设定/人物, 即可连续写 {n} 章。"
    )


def _parse_word_targets(word_targets: str, n: int) -> list[dict]:
    """解析字数配置到每章 targets.

    支持格式:
    - "2000-2200"                          → 全部章统一
    - "第1-3章2000-2200; 第4章6000-7000"   → 分章指定
    - 空                                   → 番茄默认 2000-2200
    """
    default = {"min_words": 2000, "max_words": 2200}
    result: list[dict | None] = [None] * n
    if not word_targets:
        return [dict(default) for _ in range(n)]

    for seg in re.split(r"[;；\n]", word_targets):
        seg = seg.strip()
        if not seg:
            continue
        # 分章: 第1-3章2000-2200 或 第4章6000-7000
        m = re.match(r"第(\d+)(?:-(\d+))?章\s*(\d+)-(\d+)", seg)
        if m:
            s = int(m.group(1))
            e = int(m.group(2)) if m.group(2) else s
            mn, mx = int(m.group(3)), int(m.group(4))
            for i in range(s, min(e, n) + 1):
                result[i - 1] = {"min_words": mn, "max_words": mx}
            continue
        # 全局统一: 2000-2200
        m2 = re.match(r"(\d+)-(\d+)", seg)
        if m2:
            mn, mx = int(m2.group(1)), int(m2.group(2))
            for i in range(n):
                result[i] = {"min_words": mn, "max_words": mx}

    for i in range(n):
        if result[i] is None:
            result[i] = dict(default)
    return result  # type: ignore[return-value]


def _generate_outlines(idea: str, genre: str, n: int) -> list[str]:
    """用 LLM 生成 N 章大纲列表."""
    try:
        resp = _invoke(
            _OUTLINE_GEN.format(n=n, idea=idea, genre=genre),
            "你是连载大纲生成器。",
        )
        lines = [l.strip() for l in resp.splitlines() if l.strip()]
        outlines = []
        for line in lines:
            content = re.sub(
                r"^(第?\d+章[：:]?|chapter\s*\d+[：:]?)", "", line, flags=re.IGNORECASE
            ).strip()
            if content:
                outlines.append(content)
        if len(outlines) < n:
            outlines.extend([f"第{i+1}章: 剧情推进" for i in range(len(outlines), n)])
        return outlines[:n]
    except Exception:
        return [f"第{i+1}章: 剧情推进" for i in range(n)]


# ============================================================
# ⑥ 包装
# ============================================================

@tool
def package_book(book_info: str) -> str:
    """生成书名候选 + 简介.

    Args:
        book_info: 作品信息 (题材/前提/卖点)

    Returns:
        书名候选 + 简介。
    """
    from book_packager.tools import generate_title, write_blurb
    title = generate_title.invoke({"book_info": book_info})
    blurb = write_blurb.invoke({"book_info": book_info})
    return f"## 书名候选\n{title}\n\n## 简介\n{blurb}"


# 供导演图绑定使用的工具列表
DIRECTOR_TOOLS = [
    generate_idea,
    build_world,
    build_characters,
    plan_outline,
    prepare_serial,
    package_book,
]
