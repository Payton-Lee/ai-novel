"""AI 网络小说多 Agent 协作图 — 主图定义.

流水线结构:
    START → outline → world → character → draft → review → (条件分支)
                                                          ├─ 质量达标/达到上限 → polish → END
                                                          └─ 需要重写 → draft (循环)
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from novel.nodes.character_agent import character_agent
from novel.nodes.draft_agent import draft_agent
from novel.nodes.outline_agent import outline_agent
from novel.nodes.polish_agent import polish_agent
from novel.nodes.review_agent import review_agent
from novel.nodes.world_agent import world_agent
from novel.state import NovelState

# 质量达标阈值 (满分 10)
QUALITY_THRESHOLD = 7

# 最大审稿循环次数 (避免无限重写)
MAX_ITERATIONS = 3


def _quality_gate(state: NovelState) -> str:
    """审稿后的条件路由: 达标或超限则进入润色, 否则重写.

    - quality_score >= QUALITY_THRESHOLD → 润色
    - iteration_count >= MAX_ITERATIONS → 润色 (强制通过)
    - 否则 → 回到 draft 重写
    """
    score = state.get("quality_score", 0)
    iterations = state.get("iteration_count", 0)

    if score >= QUALITY_THRESHOLD:
        return "polish"
    if iterations >= MAX_ITERATIONS:
        return "polish"
    return "draft"


def _build_graph() -> StateGraph:
    """构建小说生成流水线的 StateGraph."""
    builder = StateGraph(NovelState)

    # 注册 6 个 Agent 节点
    builder.add_node("outline", outline_agent)
    builder.add_node("world", world_agent)
    builder.add_node("character", character_agent)
    builder.add_node("draft", draft_agent)
    builder.add_node("review", review_agent)
    builder.add_node("polish", polish_agent)

    # 主流程边
    builder.add_edge(START, "outline")       # 入口 → 大纲
    builder.add_edge("outline", "world")     # 大纲 → 世界观 (fan-out 开始)
    builder.add_edge("world", "character")   # 世界观 → 人物 (fan-out 第二步)
    builder.add_edge("character", "draft")   # 人物 → 初稿 (fan-in, 三者结果合并)
    builder.add_edge("draft", "review")      # 初稿 → 审稿

    # 审稿后的条件路由
    builder.add_conditional_edges(
        "review",
        _quality_gate,
        {
            "draft": "draft",     # 不达标 → 重写
            "polish": "polish",   # 达标 → 润色
        },
    )

    builder.add_edge("polish", END)  # 润色 → 结束

    return builder


# 编译后的图实例 — LangGraph 服务器入口
graph = _build_graph().compile(name="novel_writer")
