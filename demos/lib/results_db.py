# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo results database for tracking test outcomes."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

# Database file location
DEMOS_DIR = Path(__file__).parent.parent
DB_PATH = DEMOS_DIR / ".demo-results.db"


@dataclass
class DemoResult:
    """Result of a demo run."""

    name: str
    status: str  # 'pass', 'fail', 'skip'
    title: str = ""
    duration: float = 0.0
    error: str = ""


class ResultsDB:
    """SQLite database for storing demo results."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS demo_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host TEXT NOT NULL,
                    demo_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT,
                    duration REAL,
                    error TEXT,
                    timestamp TEXT NOT NULL,
                    UNIQUE(host, demo_name)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def record(self, result: Any, host: str) -> None:
        """Record a demo result."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO demo_results
                (host, demo_name, status, title, duration, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    host,
                    result.name,
                    result.status,
                    getattr(result, "title", ""),
                    getattr(result, "duration", 0.0),
                    getattr(result, "error", ""),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_demos_to_rerun(self, demo_names: list[str], host: str) -> list[str]:
        """Get list of demos that need to be rerun (failed or not tested)."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT demo_name, status FROM demo_results
                WHERE host = ? AND demo_name IN ({})
            """.format(",".join("?" * len(demo_names))),
                [host, *demo_names],
            )
            results = {row[0]: row[1] for row in cursor.fetchall()}

            # Return demos that are not 'pass'
            to_rerun = []
            for name in demo_names:
                if results.get(name) != "pass":
                    to_rerun.append(name)
            return to_rerun
        finally:
            conn.close()

    def get_summary(self, host: str) -> dict[str, int]:
        """Get summary of results for a host."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) FROM demo_results
                WHERE host = ?
                GROUP BY status
            """,
                (host,),
            )
            summary = {"pass": 0, "fail": 0, "skip": 0}
            for row in cursor.fetchall():
                if row[0] in summary:
                    summary[row[0]] = row[1]
            return summary
        finally:
            conn.close()

    def clear_host(self, host: str) -> int:
        """Clear all results for a host. Returns count of deleted records."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM demo_results WHERE host = ?",
                (host,),
            )
            count = cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def get_failing_demos(self, host: str) -> list[str]:
        """Get list of demos that failed on a host."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT demo_name FROM demo_results
                WHERE host = ? AND status = 'fail'
            """,
                (host,),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_untested_demos(self, demo_names: list[str], host: str) -> list[str]:
        """Get list of demos that haven't been tested on a host."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT demo_name FROM demo_results
                WHERE host = ? AND demo_name IN ({})
            """.format(",".join("?" * len(demo_names))),
                [host, *demo_names],
            )
            tested = {row[0] for row in cursor.fetchall()}
            return [name for name in demo_names if name not in tested]
        finally:
            conn.close()


# Singleton instance
_db: ResultsDB | None = None


def get_results_db() -> ResultsDB:
    """Get the results database singleton."""
    global _db
    if _db is None:
        _db = ResultsDB()
    return _db


def record_demo_result(result: Any, host: str) -> None:
    """Record a demo result to the database."""
    db = get_results_db()
    db.record(result, host)
