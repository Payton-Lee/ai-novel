"""作品导出 — 把连载库导出为完整作品档案.

用法:
    .venv/bin/python scripts/export_book.py --story chenci_junlin

导出到 output/books/<story_id>/:
    setting.md   作品设定 (题材/前提/世界观/人物)
    chapters/    每章正文 (ch01.md, ch02.md ...)
    memory.md    记忆 (人物状态/伏笔/关键事件/摘要)
    README.md    索引
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serial_engine.storage import get_repository  # noqa: E402


def _export_setting(repo, story_id: str) -> str:
    story = repo.get_story(story_id)
    if not story:
        return "(无故事记录)"
    lines = [
        f"# {story_id} 作品设定",
        "",
        f"**题材**: {story.get('genre', '')}",
        f"**前提**: {story.get('premise', '')}",
        "",
        "## 世界观",
        story.get("world_bible", "") or "(无)",
        "",
        "## 人物",
    ]
    chars = story.get("characters") or []
    if chars:
        for c in chars:
            if isinstance(c, dict):
                lines.append(
                    f"- **{c.get('name','?')}** ({c.get('role','配角')}): {c.get('personality','')}"
                )
            else:
                lines.append(f"- {c}")
    else:
        lines.append("(无)")
    return "\n".join(lines)


def _export_memory(repo, story_id: str) -> str:
    lines = ["# 记忆档案", ""]

    lines.append("## 人物状态 (谁知道什么)")
    states = repo.get_character_states(story_id)
    if states:
        for c in states:
            try:
                st = json.loads(c["state_json"])
                lines.append(f"- **{c['name']}** (第{c['updated_chapter']}章): {st.get('status','')}")
                if st.get("known_info"):
                    lines.append(f"  已知: {st['known_info']}")
                if st.get("unknown_info"):
                    lines.append(f"  未知: {st['unknown_info']}")
            except json.JSONDecodeError:
                lines.append(f"- **{c['name']}**: {c['state_json']}")
    else:
        lines.append("(无)")

    lines.append("")
    lines.append("## 伏笔网络")
    threads = repo.get_plot_threads(story_id)
    if threads:
        for t in threads:
            lines.append(f"- [{t['status']}] (第{t['introduced_chapter']}章埋): {t['thread']}")
    else:
        lines.append("(无)")

    lines.append("")
    lines.append("## 关键事件")
    events = repo.get_key_events(story_id)
    if events:
        for e in events:
            lines.append(f"- 第{e['chapter_no']}章: {e['event']}")
    else:
        lines.append("(无)")

    lines.append("")
    lines.append("## 分层摘要")
    summaries = repo.get_summaries(story_id)
    for level, text in sorted(summaries.items()):
        if text:
            lines.append(f"### {level}\n{text}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出作品档案")
    parser.add_argument("--story", required=True, help="story_id")
    args = parser.parse_args()

    db = Path("output/serial") / f"{args.story}.db"
    if not db.exists():
        print(f"❌ 连载库不存在: {db}")
        return

    repo = get_repository(db)
    out_dir = Path("output/books") / args.story
    chapters_dir = out_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    # 设定
    setting = _export_setting(repo, args.story)
    (out_dir / "setting.md").write_text(setting, encoding="utf-8")

    # 章节
    chapters = repo.get_chapters(args.story, 1, 10**9)
    for ch in chapters:
        fname = chapters_dir / f"ch{ch['chapter_no']:02d}.md"
        content = f"# 第{ch['chapter_no']}章\n\n{ch['content']}\n\n---\n*字数 {ch.get('word_count',0)} | 质量分 {ch.get('quality_score',0)}*\n"
        fname.write_text(content, encoding="utf-8")

    # 记忆
    memory = _export_memory(repo, args.story)
    (out_dir / "memory.md").write_text(memory, encoding="utf-8")

    # README 索引
    readme = [
        f"# {args.story} 作品档案",
        "",
        f"**总章节数**: {len(chapters)}",
        "",
        "## 文件",
        "- [作品设定](setting.md)",
        "- [记忆档案](memory.md)",
        "- [章节](chapters/)",
        "",
        "## 章节列表",
    ]
    for ch in chapters:
        readme.append(f"- 第{ch['chapter_no']}章 (质量{ch.get('quality_score',0)}, {ch.get('word_count',0)}字)")
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")

    repo.close()
    print(f"✅ 作品已导出: {out_dir}")
    print(f"   - {len(chapters)} 章 / setting.md / memory.md / README.md")


if __name__ == "__main__":
    main()
