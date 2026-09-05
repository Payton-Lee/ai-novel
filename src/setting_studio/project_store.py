"""项目设定库 — 跨 Agent、跨会话的持久设定存储.

板块 (section): world / characters / relationships / timeline / conflicts / outline
每次改动记变更日志, 支持回看设定演化。
默认 SQLite (output/projects/<pid>.db), 抽象接口可替换。
"""

from __future__ import annotations

import sqlite3
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "output" / "projects"

# 设定库板块
SECTIONS = ("world", "characters", "relationships", "timeline", "conflicts", "outline")
SECTION_LABELS = {
    "world": "世界观",
    "characters": "人物",
    "relationships": "人物关系",
    "timeline": "时间线",
    "conflicts": "冲突推演",
    "outline": "大纲",
}


class ProjectStore(ABC):
    """项目设定库抽象接口."""

    @abstractmethod
    def create_project(self, pid: str, meta: dict) -> None: ...
    @abstractmethod
    def get_project(self, pid: str) -> Optional[dict]: ...

    @abstractmethod
    def get_setting(self, pid: str, section: str) -> str: ...
    @abstractmethod
    def save_setting(self, pid: str, section: str, text: str, change: str = "") -> None: ...
    @abstractmethod
    def all_settings(self, pid: str) -> dict: ...

    @abstractmethod
    def append_log(self, pid: str, section: str, change: str) -> None: ...
    @abstractmethod
    def get_log(self, pid: str) -> list[dict]: ...

    @abstractmethod
    def get_progress(self, pid: str) -> dict: ...

    @abstractmethod
    def close(self) -> None: ...


class SQLiteProjectStore(ProjectStore):
    """SQLite 实现."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
            db_path = DEFAULT_DIR / "projects.db"
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS project (
                id TEXT PRIMARY KEY, genre TEXT, premise TEXT, title TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS setting (
                project_id TEXT, section TEXT, content TEXT, updated_at TEXT,
                PRIMARY KEY (project_id, section)
            );
            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT, section TEXT, change TEXT, ts TEXT
            );
            """
        )
        self._conn.commit()

    def create_project(self, pid: str, meta: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO project VALUES (?,?,?,?,?)",
            (pid, meta.get("genre", ""), meta.get("premise", ""), meta.get("title", ""),
             time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()

    def get_project(self, pid: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM project WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def get_setting(self, pid: str, section: str) -> str:
        row = self._conn.execute(
            "SELECT content FROM setting WHERE project_id=? AND section=?",
            (pid, section),
        ).fetchone()
        return row["content"] if row else ""

    def save_setting(self, pid: str, section: str, text: str, change: str = "") -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO setting VALUES (?,?,?,?)",
            (pid, section, text, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        if change:
            self.append_log(pid, section, change)
        self._conn.commit()

    def all_settings(self, pid: str) -> dict:
        rows = self._conn.execute(
            "SELECT section, content FROM setting WHERE project_id=? AND content != ''",
            (pid,),
        ).fetchall()
        return {r["section"]: r["content"] for r in rows}

    def append_log(self, pid: str, section: str, change: str) -> None:
        self._conn.execute(
            "INSERT INTO change_log (project_id, section, change, ts) VALUES (?,?,?,?)",
            (pid, section, change, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()

    def get_log(self, pid: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM change_log WHERE project_id=? ORDER BY id", (pid,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_progress(self, pid: str) -> dict:
        settings = self.all_settings(pid)
        return {
            section: bool(settings.get(section))
            for section in SECTIONS
        }

    def close(self) -> None:
        self._conn.close()


def get_project_store(pid: str) -> SQLiteProjectStore:
    """打开 (或创建) 项目的设定库."""
    return SQLiteProjectStore(DEFAULT_DIR / f"{pid}.db")
