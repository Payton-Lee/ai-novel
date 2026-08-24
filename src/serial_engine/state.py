"""SerialState — 连载引擎状态."""

from typing import TypedDict

from novel.state import CharacterCard


class SerialState(TypedDict, total=False):
    """连载引擎状态.

    输入: story_id + 故事设定 + 章节大纲; 记忆从 SQLite 读取。
    mode: single(写一章) / continuous(自动连续)。
    """

    # ==== 输入 ====
    story_id: str
    genre: str
    premise: str
    world_bible: str
    characters: list[CharacterCard]
    style_guide: str
    style_mode: str  # "fanqie"(默认, 注入番茄指南) / "generic"(不注入)
    style_profile: str  # 用户样本提取的风格画像 (可选)
    mode: str  # "single" | "continuous"
    chapter_outlines: list[str]  # continuous 模式: 逐章大纲列表
    chapter_targets: list[dict]  # continuous 模式: 逐章字数目标 [{min_words, max_words}], 与 outlines 平行
    chapter_outline: str  # single 模式: 单章大纲

    # ==== 运行中 ====
    db_path: str  # SQLite 库文件路径
    chapter_no: int  # 将要写的章节号
    total_written: int  # 已写章数
    target_chapters: int  # 目标总章数
    outlines_base: int  # chapter_outlines 列表起始章号 (首次=1, 续写=written+1)
    total_target: int  # 本轮总目标章数 = 起始进度 + 本轮目标 (route 用绝对计数判断)
    mem_context: str  # 组装好的记忆上下文
    current_outline: str  # 当前章大纲
    prev_chapter_summary: str  # 上一章摘要
    contract: dict  # 本章任务单 (Chapter Contract)
    prev_diff: str  # 上章 State Diff 反馈
    reader_gate: bool  # 是否启用 reader PASS/FAIL 门控 (默认 False)
    audience: str  # 目标读者画像 (reader 门控用)
    word_check: bool  # 是否启用写后字数校验调整 (默认 True)
    reader_feedback: str  # reader 反馈
    reader_verdict: str  # "pass" / "fail"
    rewrite_count: int  # 本章当前重写次数 (reader FAIL 重写)

    # ==== 输出 ====
    final_chapter: str
    chapter_summary: str
    word_count: int
    quality_score: int
