"""Tests for the SQLite migration runner."""
from __future__ import annotations

from pathlib import Path

from app.stores.sqlite.database import SqliteDatabase


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "meta.db")

    db.migrate()
    db.migrate()

    with db.connect() as conn:
        versions = [row["version"] for row in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )]
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert versions == [1, 2]
    assert {"documents", "chunks", "theories", "claims", "findings", "links"} <= tables
    assert "chunks_fts" in tables


def test_migration_enables_wal_and_foreign_keys(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "meta.db")
    db.migrate()

    with db.connect() as conn:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]

    assert journal.lower() == "wal"
    assert fk == 1
