"""连载压力测试运行器.

用法:
    .venv/bin/python scripts/pressure_test.py --story test1 --chapters 10 \
        --genre 都市修仙 --premise "外卖员陈默被雷劈觉醒望气, 逆袭世家" \
        --world "双层世界, 地下修行世家" --characters "陈默:主角|林氏:女主|大长老:反派"
    --reader-gate   启用 reader PASS/FAIL 门控
    --deep          启用 LLM 深度检测 (OOC/套路化)
    --keep          不清库 (断点续写)

自动生成 N 章大纲 → 跑连载 → 输出四指标报告。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(str(Path(__file__).resolve().parents[1] / ".env"))

from novel.llm_factory import get_llm_from_config  # noqa: E402
from serial_engine.graph import graph  # noqa: E402
from serial_engine.pressure_report import analyze_story  # noqa: E402
from serial_engine.storage import get_repository  # noqa: E402

OUTLINE_PROMPT = """你是连载大纲生成器。为一部小说生成前 {n} 章的简短章节大纲, 每章一句话(不超过60字), 要连续推进主线, 章章有进展有钩子。

题材: {genre}
前提: {premise}

输出格式: 每行 "第X章: 内容"。不要解释。"""


def generate_outlines(genre: str, premise: str, n: int) -> list[str]:
    """用 LLM 生成 N 章大纲列表."""
    llm = get_llm_from_config()
    resp = llm.invoke(OUTLINE_PROMPT.format(n=n, genre=genre, premise=premise))
    lines = [l.strip() for l in str(resp.content).splitlines() if l.strip()]
    outlines = []
    for line in lines:
        m = re.match(r"^(第?\d+章[：:]?|chapter\s*\d+[：:]?)", line, re.IGNORECASE)
        content = re.sub(r"^(第?\d+章[：:]?|chapter\s*\d+[：:]?)", "", line, flags=re.IGNORECASE).strip()
        if content:
            outlines.append(content)
    if len(outlines) < n:
        outlines.extend([f"第{i+1}章: 剧情继续推进" for i in range(len(outlines), n)])
    return outlines[:n]


def parse_characters(char_str: str) -> list[dict]:
    """解析 "名:定位:性格|名:定位:性格" 格式."""
    if not char_str:
        return []
    chars = []
    for item in char_str.split("|"):
        parts = item.split(":")
        if len(parts) >= 1 and parts[0].strip():
            chars.append({
                "name": parts[0].strip(),
                "role": parts[1].strip() if len(parts) > 1 else "配角",
                "personality": parts[2].strip() if len(parts) > 2 else "",
            })
    return chars


def _print_report(report: dict, deep: bool) -> None:
    """打印压力测试报告."""
    print(f"story: {report['story_id']} | 总章数: {report['total_chapters']} | 健康度: {report['health']}")
    print(f"未回收伏笔: {report['open_threads']} | 已回收: {report['resolved_threads']}")

    print(f"\n-- 剧情重复 ({len(report['repetition'])}) --")
    for r in report["repetition"]:
        print(f"  第{r['chapter_from']}-{r['chapter_to']}章 相似度 {r['similarity']} ({r['level']})")

    print(f"\n-- 伏笔遗忘 ({len(report['forgotten_threads'])}) --")
    for f in report["forgotten_threads"]:
        print(f"  [{f['status']}] {f['thread'][:40]}... 最后提及第{f['last_mentioned_chapter']}章, 遗忘{f['stale_chapters']}章")

    if deep:
        print(f"\n-- 人物OOC ({len(report['ooc'])}) --")
        for o in report["ooc"]:
            print(f"  第{o.get('chapter_from')}-{o.get('chapter_to')}章 {o.get('character')}: {o.get('issue','')[:60]}")
        print(f"\n-- 章节套路化 ({len(report['formulaic'])}) --")
        for f in report["formulaic"]:
            print(f"  {f.get('chapter')}: {f.get('pattern','')[:50]}")
    else:
        print("\n(人物OOC/套路化 需 --deep 开启 LLM 深度检测)")


def main() -> None:
    parser = argparse.ArgumentParser(description="连载压力测试")
    parser.add_argument("--story", required=True, help="story_id")
    parser.add_argument("--chapters", type=int, default=10, help="章节数")
    parser.add_argument("--genre", default="都市修仙")
    parser.add_argument("--premise", default="", help="故事前提 (analyze-only 模式可省略)")
    parser.add_argument("--world", default="")
    parser.add_argument("--characters", default="", help="名:定位:性格|...")
    parser.add_argument("--reader-gate", action="store_true", help="启用 reader 门控")
    parser.add_argument("--audience", default="追爽文读者")
    parser.add_argument("--deep", action="store_true", help="LLM 深度检测 OOC/套路化")
    parser.add_argument("--keep", action="store_true", help="不清库")
    parser.add_argument("--analyze-only", action="store_true", help="只分析已有库, 不跑连载")
    args = parser.parse_args()

    # 清库 (除非 --keep / --analyze-only)
    db = Path("output/serial") / f"{args.story}.db"
    if db.exists() and not args.keep and not args.analyze_only:
        db.unlink()
        print(f"已清理旧库: {db}")

    # 只分析模式
    if args.analyze_only:
        print(f"=== 分析已有库: {args.story} ===")
        repo = get_repository(db)
        report = analyze_story(repo, args.story, deep=args.deep)
        repo.close()
        _print_report(report, args.deep)
        return

    # 生成大纲
    print(f"正在生成 {args.chapters} 章大纲...")
    outlines = generate_outlines(args.genre, args.premise, args.chapters)
    print(f"大纲: {outlines[:3]} ...")

    # 跑连载
    start = time.time()
    print(f"开始连载 {args.chapters} 章...")
    result = graph.invoke({
        "story_id": args.story,
        "genre": args.genre,
        "premise": args.premise,
        "world_bible": args.world,
        "characters": parse_characters(args.characters),
        "mode": "continuous",
        "chapter_outlines": outlines,
        "reader_gate": args.reader_gate,
        "audience": args.audience,
    }, {"configurable": {"llm_provider": "deepseek", "llm_model": "deepseek-v4-flash"}})
    elapsed = time.time() - start
    print(f"连载完成: {result.get('total_written', 0)} 章, 耗时 {elapsed:.0f}s")

    # 生成报告
    print("\n=== 压力测试报告 ===")
    repo = get_repository(db)
    report = analyze_story(repo, args.story, deep=args.deep)
    repo.close()
    _print_report(report, args.deep)

    # 保存 JSON 报告
    out_path = Path("output/serial") / f"{args.story}_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {out_path}")


if __name__ == "__main__":
    main()
