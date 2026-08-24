"""连载引擎主图 — 多章连续写作 + 分层持久记忆 + 稳定性闭环.

图结构 (稳定性增强):
    START → init(建库/读进度/取大纲)
      → mem_assemble(组装分层记忆, 含谁知道什么)
      → contract(生成章节任务单)
      → write_chapter(封装 novel 图写一章, 注入 contract)
      → reader_check(可选 PASS/FAIL 门控)
          ├─ FAIL(≤2次) → 带反馈回 write_chapter 重写
          └─ PASS → mem_update(存章 + 谁知道什么提取 + State Diff + 摘要压缩)
      → route: continuous 且未完 → 回 mem_assemble; 否则 END

持久化: SQLite (可替换), 支持断点续写。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from novel.llm_factory import get_llm_from_config
from serial_engine.contract import contract_to_text, generate_contract
from serial_engine.memory import (
    assemble_memory,
    rollup_volume_summary,
    save_chapter_summary,
)
from serial_engine.scene_rewrite import locate_problem_scenes, rewrite_scenes, split_scenes
from serial_engine.state import SerialState
from serial_engine.storage import DEFAULT_DIR, StoryRepository, get_repository
from serial_engine.word_check import adjust_to_target, count_words
from serial_engine.writer import write_chapter_with_novel

# reader 门控重写上限
MAX_REWRITES = 2


def _open_repo(state: dict) -> StoryRepository:
    """打开 (或创建) 当前故事的存储库."""
    db_path = state.get("db_path")
    return get_repository(Path(db_path) if db_path else DEFAULT_DIR / f"{state['story_id']}.db")


def _current_outline(state: dict) -> str:
    """取当前章大纲.

    连续模式: outlines_base 记录大纲列表起始章号 (首次=1, 续写=written+1),
    idx = chapter_no - outlines_base, 支持首次与续写两种场景。
    """
    outlines = state.get("chapter_outlines") or []
    if state.get("mode") == "continuous" and outlines:
        base = state.get("outlines_base", 1)
        idx = state.get("chapter_no", 1) - base
        if 0 <= idx < len(outlines):
            return outlines[idx]
        return ""
    return state.get("chapter_outline", "")


# 番茄默认字数范围 (未配置 chapter_targets 时)
DEFAULT_MIN_WORDS = 2000
DEFAULT_MAX_WORDS = 2200


def _current_target(state: dict) -> tuple[int, int]:
    """取当前章字数目标 (min_words, max_words).

    优先用 chapter_targets 逐章配置; 未配置用番茄默认 2000-2200。
    """
    targets = state.get("chapter_targets") or []
    if state.get("mode") == "continuous" and targets:
        base = state.get("outlines_base", 1)
        idx = state.get("chapter_no", 1) - base
        if 0 <= idx < len(targets):
            t = targets[idx]
            mn = int(t.get("min_words", DEFAULT_MIN_WORDS))
            mx = int(t.get("max_words", DEFAULT_MAX_WORDS))
            return max(300, mn), max(mn, mx)
    return DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS


# ============================================================
# 节点 1: 初始化
# ============================================================

def init_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """建库、写入故事元数据、读取进度 (断点续写)."""
    story_id = state["story_id"]
    db_path = str(DEFAULT_DIR / f"{story_id}.db")

    repo = get_repository(Path(db_path))
    repo.create_story(story_id, {
        "genre": state.get("genre", ""),
        "premise": state.get("premise", ""),
        "world_bible": state.get("world_bible", ""),
        "characters": state.get("characters", []),
        "style_guide": state.get("style_guide", ""),
    })
    written = repo.count_chapters(story_id)
    repo.close()

    mode = state.get("mode", "single")
    outlines = state.get("chapter_outlines") or []
    if mode == "continuous":
        target = len(outlines)
    else:
        target = 1

    return {
        "db_path": db_path,
        "chapter_no": written + 1,
        "total_written": written,
        "target_chapters": target,
        "total_target": written + target,  # 绝对总目标, route 判断用
        # 大纲列表从"下一章"开始 (首次=1, 续写=written+1)
        "outlines_base": written + 1 if (mode == "continuous" and outlines) else 1,
    }


# ============================================================
# 节点 2: 记忆组装
# ============================================================

def mem_assemble_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """组装分层记忆 (近景/中景/远景 + 动态状态 + 谁知道什么)."""
    repo = _open_repo(state)
    mem = assemble_memory(repo, state["story_id"], state.get("chapter_no", 1))
    repo.close()
    return {"mem_context": mem}


# ============================================================
# 节点 3: Chapter Contract (章节任务单)
# ============================================================

def contract_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """生成章节任务单, 并确定本章大纲."""
    outline = _current_outline(state)

    repo = _open_repo(state)
    contract = generate_contract(
        repo,
        state["story_id"],
        state.get("chapter_no", 1),
        outline,
        state.get("mem_context", ""),
        state.get("prev_diff", ""),
        config,
    )
    repo.close()

    # 注入本章字数目标 (写后校验依据)
    mn, mx = _current_target(state)
    contract["target_words"] = f"{mn}-{mx}"

    return {
        "current_outline": outline,
        "contract": contract,
        "rewrite_count": 0,
        "reader_verdict": "",
        "reader_feedback": "",
    }


# ============================================================
# 节点 4: 章节写作 (封装 novel 图)
# ============================================================

def _with_max_tokens(config: Optional[RunnableConfig], max_tokens: int) -> dict:
    """构造带 max_tokens 的 config, 让 novel 各节点读到."""
    if config is None:
        return {"configurable": {"max_tokens": max_tokens}}
    cfg = dict((config or {}).get("configurable", {}))
    cfg["max_tokens"] = max_tokens
    return {**config, "configurable": cfg}


def write_chapter_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """调用 novel 图生成一章, 注入 contract + 字数目标 + (可选) reader 重写反馈."""
    outline = state.get("current_outline") or _current_outline(state)

    # 世界观: 优先用组装好的记忆, 第1章无记忆时退回 world_bible
    world_setting = state.get("mem_context") or state.get("world_bible", "")

    # 重写时递增计数, 并入 reader 反馈作为重写约束
    rewrite_count = state.get("rewrite_count", 0)
    extra = ""
    if state.get("reader_verdict") == "fail" and state.get("reader_feedback"):
        rewrite_count += 1
        extra = (
            "## 读者反馈重写要求 (必须解决以下问题)\n"
            f"{state['reader_feedback']}"
        )

    # 本章字数目标 + max_tokens (大章节自动调高)
    mn, mx = _current_target(state)
    word_target = f"{mn}-{mx}"
    max_tokens = max(4096, int(mx * 1.8))  # 中文约1.8 token/字, 留余量
    novel_config = _with_max_tokens(config, max_tokens)

    result = write_chapter_with_novel(
        genre=state.get("genre", ""),
        premise=state.get("premise", ""),
        world_setting=world_setting,
        characters=state.get("characters", []),
        chapter_outline=outline,
        prev_chapter_summary=state.get("prev_chapter_summary", ""),
        style_guide=state.get("style_guide", ""),
        contract_text=contract_to_text(state.get("contract", {})),
        extra_constraints=extra,
        style_mode=state.get("style_mode", "fanqie"),
        style_profile=state.get("style_profile", ""),
        word_target=word_target,
        config=novel_config,
    )

    return {
        "final_chapter": result.get("final_chapter", ""),
        "chapter_summary": result.get("chapter_summary", ""),
        "word_count": result.get("chapter_word_count", 0),
        "quality_score": result.get("quality_score", 0),
        "rewrite_count": rewrite_count,
        "word_target": word_target,
    }


# ============================================================
# 节点 4.5: 写后字数校验 (可选, 默认开)
# ============================================================

def word_check_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """写后校验字数, 超目标范围自动压缩/扩写."""
    if not state.get("word_check", True):
        return {}
    content = state.get("final_chapter", "")
    if not content:
        return {}
    mn, mx = _current_target(state)
    adjusted = adjust_to_target(content, mn, mx, config)
    if adjusted != content:
        return {"final_chapter": adjusted, "word_count": count_words(adjusted)}
    return {}


# ============================================================
# 节点 5: reader PASS/FAIL 门控 (可选)
# ============================================================

def _parse_verdict(report: str) -> str:
    """从 reader 报告判断追读率预测: 含"低" → fail, 否则 pass."""
    if "追读率预测" in report:
        seg = report.split("追读率预测")[1][:20]
        if "低" in seg:
            return "fail"
    return "pass"


def reader_check_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """可选: 用 reader_simulator 评估章节, 决定 PASS/FAIL."""
    if not state.get("reader_gate"):
        return {"reader_verdict": "pass", "reader_feedback": ""}

    from reader_simulator.tools import assess_chapter

    report = assess_chapter.invoke({
        "text": state.get("final_chapter", ""),
        "genre": state.get("genre", ""),
        "audience": state.get("audience", "追爽文读者"),
    })
    return {"reader_feedback": report, "reader_verdict": _parse_verdict(report)}


def _reader_route(state: SerialState) -> str:
    """reader FAIL 且未超重写上限 → 场景级重写; 否则进 mem_update."""
    if state.get("reader_verdict") == "fail" and state.get("rewrite_count", 0) < MAX_REWRITES:
        return "scene_rewrite"
    return "mem_update"


# ============================================================
# 节点 5.5: 场景级重写 (reader FAIL 时只改问题场景)
# ============================================================

def scene_rewrite_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """定位并重写问题场景, 其余保持原样; 重写后回 reader 再评估."""
    content = state.get("final_chapter", "")
    feedback = state.get("reader_feedback", "")
    rewrite_count = state.get("rewrite_count", 0) + 1

    if not content or len(split_scenes(content)) <= 1:
        # 章节太短无法切场景, 退回整章重写 (带 reader 反馈)
        return {"rewrite_count": rewrite_count, "reader_verdict": "rewrite_full"}

    problem_ids = locate_problem_scenes(content, feedback, config)
    if problem_ids:
        new_content = rewrite_scenes(content, problem_ids, feedback, config)
        if new_content != content:
            return {"final_chapter": new_content, "rewrite_count": rewrite_count}
    # 未定位到问题场景 → 保持原文, 进 mem_update
    return {"rewrite_count": rewrite_count, "reader_verdict": "pass"}


# ============================================================
# 状态提取 (每章一次 LLM 调用, 维护动态记忆 + 谁知道什么)
# ============================================================

_EXTRACT_PROMPT = """你是连载故事的状态跟踪器。从章节中提取**本章新增或变化**的结构化状态, 只输出 JSON, 不要任何解释文字。

章节内容:
{content}

输出 JSON 格式 (严格):
{{
  "character_states": [
    {{"name": "角色名", "status": "当前状态, 如修为/位置/健康/关系变化",
     "known_info": ["本章此角色新知道的1-2条信息"], "unknown_info": ["本章明确此角色仍不知道/被隐瞒的信息"]}}
  ],
  "plot_threads": [{{"thread": "伏笔内容", "status": "in_progress 或 resolved 或 unresolved"}}],
  "key_events": [{{"event": "重大事件", "impact": "对主线的影响"}}],
  "factions": [{{"name": "势力名", "status": "势力当前状态"}}]
}}

规则:
- 只提取本章新增或发生变化的条目, 不要重复之前的既有状态
- known_info/unknown_info 只记录**本章明确体现**的信息; 无则空数组
- 没有变化的维度返回空数组 []
- 角色/势力名保持稳定命名
- JSON 必须是合法可解析的"""


def _extract_state(content: str) -> dict[str, list[dict]]:
    """用 LLM 从章节提取动态状态; 失败时返回空."""
    if not content:
        return {"character_states": [], "plot_threads": [], "key_events": [], "factions": []}
    try:
        llm = get_llm_from_config()
        resp = llm.invoke([
            SystemMessage(content="你是连载故事状态提取器。只输出合法 JSON。"),
            HumanMessage(content=_EXTRACT_PROMPT.format(content=content[:8000])),
        ])
        text = str(resp.content)
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {"character_states": [], "plot_threads": [], "key_events": [], "factions": []}
        data = json.loads(m.group(0))
        return {
            "character_states": data.get("character_states", []),
            "plot_threads": data.get("plot_threads", []),
            "key_events": data.get("key_events", []),
            "factions": data.get("factions", []),
        }
    except Exception:
        return {"character_states": [], "plot_threads": [], "key_events": [], "factions": []}


# ============================================================
# State Diff (contract 预期 vs 实际变化)
# ============================================================

def _compute_diff(contract: dict, extracted: dict) -> str:
    """对比 contract 预期变化 vs 实际提取, 生成差异反馈."""
    expected = (contract or {}).get("expected_character_changes", []) or []
    actual_map = {c.get("name"): c for c in extracted.get("character_states", []) if c.get("name")}

    lines: list[str] = []
    for e in expected:
        name = e.get("name")
        if not name:
            continue
        if name in actual_map:
            lines.append(f"✅ {name}: 预期 {e.get('from','?')}→{e.get('to','?')} 已发生 ({actual_map[name].get('status','')[:40]})")
        else:
            lines.append(f"⚠️ {name}: 预期变化未落实 ({e.get('from','?')}→{e.get('to','?')})")
    for name, a in actual_map.items():
        if name not in {e.get("name") for e in expected}:
            lines.append(f"➕ {name}: 意外变化 ({a.get('status','')[:40]})")

    return "\n".join(lines) if lines else "无预期的人物状态变化"


# ============================================================
# 节点 6: 记忆更新
# ============================================================

def mem_update_node(state: SerialState, config: Optional[RunnableConfig] = None) -> dict:
    """存章节、提取动态状态 (含谁知道什么)、State Diff、压缩摘要; 推进下一章."""
    story_id = state["story_id"]
    ch = state.get("chapter_no", 1)
    content = state.get("final_chapter", "")
    summary = state.get("chapter_summary", "")

    repo = _open_repo(state)
    # 存章节
    repo.save_chapter(story_id, ch, {
        "content": content,
        "summary": summary,
        "word_count": state.get("word_count", 0),
        "quality_score": state.get("quality_score", 0),
    })
    # 存章节摘要
    save_chapter_summary(repo, story_id, ch, summary)

    # 提取动态状态 (含 谁知道什么)
    extracted = _extract_state(content)
    for c in extracted.get("character_states", []):
        if c.get("name"):
            repo.update_character_state(story_id, c["name"], json.dumps(c, ensure_ascii=False), ch)
    for t in extracted.get("plot_threads", []):
        if t.get("thread"):
            repo.upsert_plot_thread(story_id, t["thread"], t.get("status", "in_progress"), ch)
    for e in extracted.get("key_events", []):
        repo.add_key_event(story_id, ch, e.get("event", ""), e.get("impact", ""))
    for f in extracted.get("factions", []):
        if f.get("name"):
            repo.update_faction(story_id, f["name"], json.dumps(f, ensure_ascii=False), ch)

    # State Diff: contract 预期 vs 实际 → 存反馈, 供下一章 contract
    diff = _compute_diff(state.get("contract", {}), extracted)
    if diff != "无预期的人物状态变化":
        repo.add_key_event(story_id, ch, "[状态差异] " + diff.replace("\n", " | "), "下一章任务单参考")

    # 摘要分层压缩
    rollup_volume_summary(repo, story_id, ch)
    repo.close()

    return {
        "total_written": ch,
        "prev_chapter_summary": summary,
        "chapter_no": ch + 1,
        "prev_diff": diff,
        "reader_verdict": "pass",  # 进入下一章前重置
        "rewrite_count": 0,
    }


# ============================================================
# 路由
# ============================================================

def _route(state: SerialState) -> str:
    """continuous 且未写完 → 继续; 否则结束. (用绝对计数 total_target 判断, 支持续写)"""
    if state.get("mode") == "continuous":
        if state.get("total_written", 0) < state.get("total_target", 0):
            return "mem_assemble"
    return END


def _build_graph() -> StateGraph:
    builder = StateGraph(SerialState)
    builder.add_node("init", init_node)
    builder.add_node("mem_assemble", mem_assemble_node)
    builder.add_node("contract", contract_node)
    builder.add_node("write_chapter", write_chapter_node)
    builder.add_node("word_check", word_check_node)
    builder.add_node("reader_check", reader_check_node)
    builder.add_node("scene_rewrite", scene_rewrite_node)
    builder.add_node("mem_update", mem_update_node)

    builder.add_edge(START, "init")
    builder.add_edge("init", "mem_assemble")
    builder.add_edge("mem_assemble", "contract")
    builder.add_edge("contract", "write_chapter")
    builder.add_edge("write_chapter", "word_check")
    builder.add_edge("word_check", "reader_check")
    builder.add_conditional_edges(
        "reader_check",
        _reader_route,
        {"scene_rewrite": "scene_rewrite", "mem_update": "mem_update"},
    )
    builder.add_edge("scene_rewrite", "reader_check")
    builder.add_conditional_edges(
        "mem_update",
        _route,
        {"mem_assemble": "mem_assemble", "__end__": END},
    )
    return builder


# 编译图 — 无自定义 checkpointer (LangGraph 平台自动持久化; 连载记忆由 SQLite 承担)
graph = _build_graph().compile(name="serial_engine")
