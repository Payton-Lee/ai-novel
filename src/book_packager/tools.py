"""发布包装器的四个工具 — 书名/简介/章节标题/金句."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from novel.llm_factory import get_llm_from_config
from book_packager.prompts import PACKAGER_SYSTEM_PROMPT


def _invoke(prompt: str) -> str:
    llm = get_llm_from_config()
    resp = llm.invoke([
        SystemMessage(content=PACKAGER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return resp.content


@tool
def generate_title(book_info: str) -> str:
    """生成 3-5 个网文风格书名候选 (含风格标注).

    Args:
        book_info: 作品信息 (题材/前提/主角/核心卖点/目标读者)

    Returns:
        书名候选列表, 每个标注风格和适合的平台。
    """
    return _invoke(
        f"作品信息:\n{book_info}\n\n请给出 3-5 个书名候选, 每个标注风格和一句话理由。"
    )


@tool
def write_blurb(book_info: str) -> str:
    """根据作品信息写 200-400 字简介 (黄金三章浓缩, 吸引点击).

    Args:
        book_info: 作品信息 (题材/前提/主角/前几章钩子)

    Returns:
        可直接用的简介。
    """
    return _invoke(
        f"作品信息:\n{book_info}\n\n请写一段 200-400 字的简介, 结构: 主角+变故+欲望+障碍+悬念收尾。"
    )


@tool
def generate_chapter_titles(book_info: str, outlines: str) -> str:
    """为给定章节大纲批量生成钩子化章节标题.

    Args:
        book_info: 作品信息 (题材/风格)
        outlines: 章节大纲列表 (每行一章, 或 markdown 大纲)

    Returns:
        每章对应的标题列表 (钩子化, 长短交替)。
    """
    return _invoke(
        f"作品信息:\n{book_info}\n\n章节大纲:\n{outlines}\n\n"
        "请为每一章生成一个钩子化标题, 格式: 第X章: 标题。长短交替, 勾起好奇心。"
    )


@tool
def extract_hooks(book_info: str, chapters: str) -> str:
    """从章节内容提取金句与宣传语.

    Args:
        book_info: 作品信息 (题材)
        chapters: 章节文本 (可多章)

    Returns:
        2-3 句金句 + 1 句平台推荐语。
    """
    return _invoke(
        f"作品信息:\n{book_info}\n\n章节内容:\n{chapters[:8000]}\n\n"
        "请提取 2-3 句有冲击力的金句 (原文或高度浓缩), 并给一句平台推荐语。"
    )


PACKAGER_TOOLS = [generate_title, write_blurb, generate_chapter_titles, extract_hooks]
