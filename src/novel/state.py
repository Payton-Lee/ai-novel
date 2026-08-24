"""NovelState — 小说生成流水线的状态定义."""

from typing import Annotated, TypedDict


class CharacterCard(TypedDict, total=False):
    """单个人物设定."""

    name: str
    role: str  # 主角/女主/反派/配角
    personality: str
    background: str
    speech_style: str  # 语言风格特征
    current_status: str  # 当前状态(随剧情更新)


class PlotThread(TypedDict):
    """伏笔/线索追踪条目."""

    thread: str  # 线索描述
    introduced_chapter: int  # 引入章节
    status: str  # "unresolved" / "resolved" / "in_progress"


def _merge_list(old: list, new: list) -> list:
    """列表合并 reducer — 追加新元素."""
    return old + new


class NovelState(TypedDict, total=False):
    """小说生成流水线的完整状态.

    分为三层:
    - 输入层: 用户提供的原始设定
    - 中间层: Agent 协作过程中产生的中间产物
    - 输出层: 最终交付的章节内容
    """

    # ========== 输入 ==========
    genre: str  # 题材: 玄幻/都市/仙侠/科幻/历史...
    premise: str  # 故事前提 (一句话简介)
    world_setting: str  # 世界观设定描述
    characters: list[CharacterCard]  # 人物设定列表
    chapter_outline: str  # 本章大纲/情节走向
    style_guide: str  # 风格要求 (可选, 如"类似辰东的写法")
    prev_chapter_summary: str  # 前一章摘要 (第一章留空)

    # ========== 中间产物 ==========
    detailed_outline: str  # 大纲Agent细化后的章节大纲
    world_bible: str  # 世界观Agent构建的世界圣经
    character_cards: str  # 人物Agent生成的人物卡片 (含语言风格)
    plot_tracker: Annotated[list[PlotThread], _merge_list]  # 伏笔/线索追踪
    current_draft: str  # 初稿Agent生成的草稿
    review_feedback: str  # 审稿Agent的审稿意见
    quality_score: int  # 审稿评分 (1-10)
    iteration_count: int  # 审稿循环计数器

    # ========== 输出 ==========
    final_chapter: str  # 润色Agent输出的最终章节
    chapter_summary: str  # 章节摘要 (供后续章节参考)
    chapter_word_count: int  # 正文字数
