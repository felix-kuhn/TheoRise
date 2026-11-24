"""SQLite-backed runtime config, LLM cache and token usage."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ...schemas.config import AppConfig
from .database import SqliteDatabase

_CONFIG_KEY = "app_config"
_SECRET_EXCLUDE = {
    "chat": {"api_key"},
    "extraction": {"api_key"},
    "linking": {"api_key"},
    "embedding": {"api_key"},
    "rerank": {"api_key"},
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RuntimeStore:
    """Runtime persistence used by the config service and gateway."""

    def __init__(self, data_dir: str | Path) -> None:
        self.db = SqliteDatabase(Path(data_dir) / "runtime.db")
        self.db.migrate()

    def load_config(self) -> AppConfig | None:
        value = self.get_setting(_CONFIG_KEY)
        if value is None:
            return None
        return AppConfig.model_validate_json(value)

    def save_config(self, config: AppConfig) -> None:
        self.set_setting(_CONFIG_KEY, config.model_dump_json(exclude=_SECRET_EXCLUDE))

    def get_setting(self, key: str) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _now()),
            )

    def cache_get(self, key: str) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT response_json FROM llm_cache WHERE key = ?",
                (key,),
            ).fetchone()
        return str(row["response_json"]) if row else None

    def cache_set(self, key: str, response_json: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_cache (key, response_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (key, response_json, _now()),
            )

    def record_usage(
        self,
        *,
        job_id: str,
        role: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        model: str,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO usage (
                    job_id, role, prompt_tokens, completion_tokens,
                    total_tokens, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    role,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    model,
                    _now(),
                ),
            )

    def usage_total(self, job_id: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(total_tokens), 0) AS total FROM usage WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return int(row["total"])

    def close(self) -> None:
        """No-op for API compatibility; connections are per operation."""
        return None
