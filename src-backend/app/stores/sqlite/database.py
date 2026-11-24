"""Small SQLite helper with a numbered migration runner."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .migrations import MIGRATIONS


class SqliteDatabase:
    """Owns the connection settings and applies migrations once."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrated = False

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def migrate(self) -> None:
        if self._migrated:
            return
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
            for version, statement in MIGRATIONS:
                if version in applied:
                    continue
                conn.executescript(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, _now()),
                )
        self._migrated = True


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
