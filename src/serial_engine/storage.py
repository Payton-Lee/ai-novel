"""连载引擎存储层 — 可替换数据库抽象.

默认实现: SQLiteStoryRepository (标准库 sqlite3, 零依赖, 支撑几万章)。
线上需要时可替换: 实现 StoryRepository 接口即可 (如 MySQLStoryRepository)。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

# 默认存储目录: output/serial/<story_id>.db
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "output" / "serial"


class StoryRepository(ABC):
    """故事持久化的抽象接口 — 数据库可替换的关键."""

    @abstractmethod
    def create_story(self, story_id: str, meta: dict) -> None: ...
    @abstractmethod
    def get_story(self, story_id: str) -> Optional[dict]: ...

    @abstractmethod
    def save_chapter(self, story_id: str, chapter_no: int, data: dict) -> None: ...
    @abstractmethod
    def get_chapters(self, story_id: str, start: int, end: int) -> list[dict]: ...
    @abstractmethod
    def get_chapter(self, story_id: str, chapter_no: int) -> Optional[dict]: ...
    @abstractmethod
    def count_chapters(self, story_id: str) -> int: ...

    @abstractmethod
    def update_character_state(self, story_id: str, name: str, state_json: str, chapter_no: int) -> None: ...
    @abstractmethod
    def get_character_states(self, story_id: str) -> list[dict]: ...

    @abstractmethod
    def upsert_plot_thread(self, story_id: str, thread: str, status: str, chapter_no: int) -> None: ...
    @abstractmethod
    def get_plot_threads(self, story_id: str) -> list[dict]: ...

    @abstractmethod
    def add_key_event(self, story_id: str, chapter_no: int, event: str, impact: str) -> None: ...
    @abstractmethod
    def get_key_events(self, story_id: str) -> list[dict]: ...

    @abstractmethod
    def update_faction(self, story_id: str, name: str, state_json: str, chapter_no: int) -> None: ...
    @abstractmethod
    def get_factions(self, story_id: str) -> list[dict]: ...

    @abstractmethod
    def save_summary(self, story_id: str, level: str, summary: str) -> None: ...
    @abstractmethod
    def get_summary(self, story_id: str, level: str) -> Optional[str]: ...
    @abstractmethod
    def get_summaries(self, story_id: str) -> dict: ...

    @abstractmethod
    def close(self) -> None: ...


def get_repository(db_path: Optional[Path] = None) -> StoryRepository:
    """创建默认存储库 (SQLite). db_path 为空时用 output/serial/<默认>.db."""
    return SQLiteStoryRepository(db_path)


class SQLiteStoryRepository(StoryRepository):
    """SQLite 实现 — 单文件库, 支撑几万章, 支持断点续写."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
            db_path = DEFAULT_DIR / "stories.db"
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS story (
                id TEXT PRIMARY KEY, genre TEXT, premise TEXT, world_bible TEXT,
                characters_json TEXT, style_guide TEXT, title TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chapter (
                story_id TEXT, chapter_no INTEGER, title TEXT, content TEXT,
                summary TEXT, word_count INTEGER, quality_score INTEGER, created_at TEXT,
                PRIMARY KEY (story_id, chapter_no)
            );
            CREATE TABLE IF NOT EXISTS character_state (
                story_id TEXT, name TEXT, state_json TEXT, updated_chapter INTEGER,
                PRIMARY KEY (story_id, name)
            );
            CREATE TABLE IF NOT EXISTS plot_thread (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id TEXT, thread TEXT, introduced_chapter INTEGER,
                status TEXT, updated_chapter INTEGER
            );
            CREATE TABLE IF NOT EXISTS key_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id TEXT, chapter_no INTEGER, event TEXT, impact TEXT
            );
            CREATE TABLE IF NOT EXISTS faction_state (
                story_id TEXT, name TEXT, state_json TEXT, updated_chapter INTEGER,
                PRIMARY KEY (story_id, name)
            );
            CREATE TABLE IF NOT EXISTS summary (
                story_id TEXT, level TEXT, summary TEXT,
                PRIMARY KEY (story_id, level)
            );
            """
        )
        self._conn.commit()

    # ---------- story ----------
    def create_story(self, story_id: str, meta: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO story VALUES (?,?,?,?,?,?,?,?)",
            (
                story_id,
                meta.get("genre", ""),
                meta.get("premise", ""),
                meta.get("world_bible", ""),
                json.dumps(meta.get("characters", []), ensure_ascii=False),
                meta.get("style_guide", ""),
                meta.get("title", ""),
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        self._conn.commit()

    def get_story(self, story_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM story WHERE id=?", (story_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["characters"] = json.loads(d.get("characters_json") or "[]")
        except json.JSONDecodeError:
            d["characters"] = []
        return d

    # ---------- chapter ----------
    def save_chapter(self, story_id: str, chapter_no: int, data: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO chapter VALUES (?,?,?,?,?,?,?,?)",
            (
                story_id, chapter_no, data.get("title", ""), data.get("content", ""),
                data.get("summary", ""), data.get("word_count", 0),
                data.get("quality_score", 0), time.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        self._conn.commit()

    def get_chapters(self, story_id: str, start: int, end: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM chapter WHERE story_id=? AND chapter_no>=? AND chapter_no<=? ORDER BY chapter_no",
            (story_id, start, end),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_chapter(self, story_id: str, chapter_no: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM chapter WHERE story_id=? AND chapter_no=?",
            (story_id, chapter_no),
        ).fetchone()
        return dict(row) if row else None

    def count_chapters(self, story_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM chapter WHERE story_id=?", (story_id,)
        ).fetchone()
        return row["c"] if row else 0

    # ---------- character state ----------
    def update_character_state(self, story_id: str, name: str, state_json: str, chapter_no: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO character_state VALUES (?,?,?,?)",
            (story_id, name, state_json, chapter_no),
        )
        self._conn.commit()

    def get_character_states(self, story_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM character_state WHERE story_id=?", (story_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- plot thread ----------
    def upsert_plot_thread(self, story_id: str, thread: str, status: str, chapter_no: int) -> None:
        # 同名伏笔: 更新状态; 否则新增
        existing = self._conn.execute(
            "SELECT id FROM plot_thread WHERE story_id=? AND thread=?",
            (story_id, thread),
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE plot_thread SET status=?, updated_chapter=? WHERE id=?",
                (status, chapter_no, existing["id"]),
            )
        else:
            self._conn.execute(
                "INSERT INTO plot_thread (story_id, thread, introduced_chapter, status, updated_chapter) VALUES (?,?,?,?,?)",
                (story_id, thread, chapter_no, status, chapter_no),
            )
        self._conn.commit()

    def get_plot_threads(self, story_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM plot_thread WHERE story_id=? ORDER BY id", (story_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- key event ----------
    def add_key_event(self, story_id: str, chapter_no: int, event: str, impact: str) -> None:
        self._conn.execute(
            "INSERT INTO key_event (story_id, chapter_no, event, impact) VALUES (?,?,?,?)",
            (story_id, chapter_no, event, impact),
        )
        self._conn.commit()

    def get_key_events(self, story_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM key_event WHERE story_id=? ORDER BY chapter_no", (story_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- faction ----------
    def update_faction(self, story_id: str, name: str, state_json: str, chapter_no: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO faction_state VALUES (?,?,?,?)",
            (story_id, name, state_json, chapter_no),
        )
        self._conn.commit()

    def get_factions(self, story_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM faction_state WHERE story_id=?", (story_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- summary ----------
    def save_summary(self, story_id: str, level: str, summary: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO summary VALUES (?,?,?)",
            (story_id, level, summary),
        )
        self._conn.commit()

    def get_summary(self, story_id: str, level: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT summary FROM summary WHERE story_id=? AND level=?", (story_id, level)
        ).fetchone()
        return row["summary"] if row else None

    def get_summaries(self, story_id: str) -> dict:
        rows = self._conn.execute(
            "SELECT level, summary FROM summary WHERE story_id=?", (story_id,)
        ).fetchall()
        return {r["level"]: r["summary"] for r in rows}

    def close(self) -> None:
        self._conn.close()

    @property
    def path(self) -> str:
        return self._path
