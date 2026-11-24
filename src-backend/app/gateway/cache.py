"""LLM response cache backed by the SQLite runtime store."""
from __future__ import annotations

from ..stores.sqlite.runtime_store import RuntimeStore


class LLMCache:
    """Thin cache API used by tests and future pipelines."""

    def __init__(self, runtime_store: RuntimeStore) -> None:
        self.runtime_store = runtime_store

    def get(self, key: str) -> str | None:
        return self.runtime_store.cache_get(key)

    def set(self, key: str, response_json: str) -> None:
        self.runtime_store.cache_set(key, response_json)
