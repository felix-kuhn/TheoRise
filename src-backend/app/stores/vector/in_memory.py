"""In-memory vector store used for tests and as an emergency fallback."""
from __future__ import annotations

import re
from typing import Any

import numpy as np

from ...pipelines.retrieval.fusion import fuse
from ..interfaces import Hit, IndexStaleError, VectorRow

_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)
_FILTER_KEYS = {"doc_id", "source_group", "kind"}


class InMemoryVectorStore:
    """A deterministic numpy-backed implementation of :class:`VectorStore`."""

    def __init__(self) -> None:
        self._rows: dict[str, VectorRow] = {}
        self._dim: int | None = None
        self._fingerprint: str | None = None

    def ensure(self, dim: int, fingerprint: str) -> None:
        if self._dim is not None and self._dim != dim:
            raise IndexStaleError(
                f"vector dimension changed ({self._dim} -> {dim}); rebuild required"
            )
        if self._fingerprint is not None and self._fingerprint != fingerprint:
            raise IndexStaleError("embedding fingerprint changed; rebuild required")
        self._dim = dim
        self._fingerprint = fingerprint

    def upsert(self, rows: list[VectorRow]) -> None:
        for row in rows:
            vector = np.asarray(row.vector, dtype=np.float32)
            if vector.ndim != 1:
                raise ValueError("vector must be one-dimensional")
            if self._dim is not None and vector.shape[0] != self._dim:
                raise IndexStaleError(
                    f"vector dimension {vector.shape[0]} != expected {self._dim}"
                )
            self._rows[row.id] = VectorRow(
                id=row.id,
                vector=vector,
                text=row.text,
                doc_id=row.doc_id,
                source_group=row.source_group,
                kind=row.kind,
                heading_path=row.heading_path,
                metadata=dict(row.metadata),
            )

    def delete_by_doc(self, doc_id: str) -> None:
        stale = [row_id for row_id, row in self._rows.items() if row.doc_id == doc_id]
        for row_id in stale:
            del self._rows[row_id]

    def search_dense(
        self, vec: list[float], k: int, filters: dict[str, Any] | None = None
    ) -> list[Hit]:
        query = np.asarray(vec, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        query = query / query_norm
        scored: list[tuple[float, VectorRow]] = []
        for row in self._rows.values():
            if not self._matches(row, filters):
                continue
            norm = np.linalg.norm(row.vector)
            similarity = float(np.dot(query, row.vector) / (norm or 1.0))
            scored.append((similarity, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [self._to_hit(row, score) for score, row in scored[:k]]

    def search_fts(
        self, query: str, k: int, filters: dict[str, Any] | None = None
    ) -> list[Hit]:
        tokens = [t for t in _WORD_RE.split(query.lower()) if t]
        scored: list[tuple[float, VectorRow]] = []
        for row in self._rows.values():
            if not self._matches(row, filters):
                continue
            text = row.text.lower()
            score = float(sum(1 for token in tokens if token in text))
            if query.lower() and query.lower() in text:
                score += 0.5
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda pair: (pair[0], pair[1].id), reverse=True)
        return [self._to_hit(row, score) for score, row in scored[:k]]

    def search_hybrid(
        self,
        vec: list[float],
        query: str,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        dense = self.search_dense(vec, k * 2, filters)
        fts = self.search_fts(query, k * 2, filters)
        dense_items = [self._hit_to_dict(hit) for hit in dense]
        fts_items = [self._hit_to_dict(hit) for hit in fts]
        fused = fuse([dense_items, fts_items], k=60)
        return [self._dict_to_hit(item) for item in fused[:k]]

    def count(self) -> int:
        return len(self._rows)

    def drop(self) -> None:
        self._rows.clear()
        self._dim = None
        self._fingerprint = None

    @staticmethod
    def _matches(row: VectorRow, filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if key not in _FILTER_KEYS:
                continue
            actual = getattr(row, key)
            expected = [value] if isinstance(value, (str, int)) else list(value)
            if actual not in expected:
                return False
        return True

    @staticmethod
    def _to_hit(row: VectorRow, score: float) -> Hit:
        return Hit(
            id=row.id,
            score=score,
            text=row.text,
            doc_id=row.doc_id,
            source_group=row.source_group,
            kind=row.kind,
            heading_path=row.heading_path,
            metadata=dict(row.metadata),
        )

    @staticmethod
    def _hit_to_dict(hit: Hit) -> dict[str, Any]:
        return {
            "id": hit.id,
            "score": hit.score,
            "text": hit.text,
            "doc_id": hit.doc_id,
            "source_group": hit.source_group,
            "kind": hit.kind,
            "heading_path": hit.heading_path,
            "metadata": hit.metadata,
        }

    @staticmethod
    def _dict_to_hit(item: dict[str, Any]) -> Hit:
        return Hit(
            id=str(item["id"]),
            score=float(item["score"]),
            text=str(item.get("text", "")),
            doc_id=str(item.get("doc_id", "")),
            source_group=str(item.get("source_group", "A")),
            kind=str(item.get("kind", "chunk")),
            heading_path=str(item.get("heading_path", "")),
            metadata=dict(item.get("metadata", {})),
        )
