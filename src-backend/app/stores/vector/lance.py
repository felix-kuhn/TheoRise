"""LanceDB-backed vector store with FTS and optional ANN indexing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
from lancedb.index import FTS, IvfPq

from ...pipelines.retrieval.fusion import fuse
from ..interfaces import Hit, IndexStaleError, VectorRow

_TABLE_NAME = "vectors"
_FILTER_KEYS = {"doc_id", "source_group", "kind"}


class LanceVectorStore:
    """A LanceDB implementation of :class:`VectorStore`."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        ann_index_threshold: int = 256,
        fts_index_min_rows: int = 20,
    ) -> None:
        import lancedb

        self._db_path = Path(data_dir) / "lancedb"
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self._db_path))
        self._fingerprint_path = self._db_path / ".fingerprint.json"
        self._ann_index_threshold = ann_index_threshold
        self._fts_index_min_rows = fts_index_min_rows
        self._fts_ready = False

    def ensure(self, dim: int, fingerprint: str) -> None:
        if self._table_exists():
            table = self._table()
            field = table.schema.field("vector")
            if not isinstance(field.type, pa.FixedSizeListType):
                raise IndexStaleError("vector column is not a fixed-size list")
            if field.type.list_size != dim:
                raise IndexStaleError(
                    f"vector dimension changed ({field.type.list_size} -> {dim}); rebuild required"
                )
            stored = self._read_fingerprint()
            if stored is not None and stored != fingerprint:
                raise IndexStaleError("embedding fingerprint changed; rebuild required")
        else:
            self._create_table(dim)
        self._write_fingerprint(fingerprint)

    def upsert(self, rows: list[VectorRow]) -> None:
        if not rows:
            return
        table = self._table()
        records = [self._row_to_record(row) for row in rows]
        table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(
            records
        )
        self._maybe_create_fts(table)
        self._maybe_create_ann(table)

    def delete_by_doc(self, doc_id: str) -> None:
        if not self._table_exists():
            return
        self._table().delete(f"doc_id = '{self._escape(doc_id)}'")

    def search_dense(
        self, vec: list[float], k: int, filters: dict[str, Any] | None = None
    ) -> list[Hit]:
        if not self._table_exists():
            return []
        rows = (
            self._table()
            .search(vec)
            .where(self._build_where(filters))
            .limit(k)
            .to_list()
        )
        return [self._record_to_hit(row, 1.0 - float(row["_distance"])) for row in rows]

    def search_fts(
        self, query: str, k: int, filters: dict[str, Any] | None = None
    ) -> list[Hit]:
        if not self._table_exists():
            return []
        table = self._table()
        self._ensure_fts(table)
        rows = (
            table.search(query, query_type="fts")
            .where(self._build_where(filters))
            .limit(k)
            .to_list()
        )
        return [self._record_to_hit(row, float(row.get("_score", 0.0))) for row in rows]

    def search_hybrid(
        self,
        vec: list[float],
        query: str,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        dense = self.search_dense(vec, k * 2, filters)
        fts = self.search_fts(query, k * 2, filters)
        fused = fuse(
            [
                [self._hit_to_dict(hit) for hit in dense],
                [self._hit_to_dict(hit) for hit in fts],
            ],
            k=60,
        )
        return [self._dict_to_hit(item) for item in fused[:k]]

    def count(self) -> int:
        if not self._table_exists():
            return 0
        return self._table().count_rows()

    def drop(self) -> None:
        if self._table_exists():
            self._db.drop_table(_TABLE_NAME)
        self._fingerprint_path.unlink(missing_ok=True)
        self._fts_ready = False

    def _table_exists(self) -> bool:
        return _TABLE_NAME in self._db.list_tables().tables

    def _table(self) -> Any:
        return self._db.open_table(_TABLE_NAME)

    def _create_table(self, dim: int) -> None:
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
                pa.field("text", pa.string()),
                pa.field("doc_id", pa.string()),
                pa.field("source_group", pa.string()),
                pa.field("kind", pa.string()),
                pa.field("heading_path", pa.string()),
                pa.field("metadata", pa.string()),
            ]
        )
        self._db.create_table(_TABLE_NAME, schema=schema)
        self._fts_ready = False

    def _maybe_create_fts(self, table: Any) -> None:
        if self._fts_ready:
            return
        if table.count_rows() < self._fts_index_min_rows:
            return
        try:
            table.create_index("text", config=FTS())
            self._fts_ready = True
        except Exception:
            # Some deployments may not ship the tantivy-backed FTS index; dense
            # search still works and the store reports a degraded FTS surface.
            return

    def _ensure_fts(self, table: Any) -> None:
        if not self._fts_ready and table.count_rows() >= self._fts_index_min_rows:
            self._maybe_create_fts(table)

    def _maybe_create_ann(self, table: Any) -> None:
        if table.count_rows() < self._ann_index_threshold:
            return
        try:
            table.create_index("vector", config=IvfPq(distance_type="cosine"))
        except Exception:
            return

    def _row_to_record(self, row: VectorRow) -> dict[str, Any]:
        vector = np.asarray(row.vector, dtype=np.float32).tolist()
        return {
            "id": row.id,
            "vector": vector,
            "text": row.text,
            "doc_id": row.doc_id,
            "source_group": row.source_group,
            "kind": row.kind,
            "heading_path": row.heading_path,
            "metadata": json.dumps(row.metadata, ensure_ascii=False),
        }

    @staticmethod
    def _record_to_hit(row: dict[str, Any], score: float) -> Hit:
        metadata = row.get("metadata", "{}")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        return Hit(
            id=str(row["id"]),
            score=score,
            text=str(row.get("text", "")),
            doc_id=str(row.get("doc_id", "")),
            source_group=str(row.get("source_group", "A")),
            kind=str(row.get("kind", "chunk")),
            heading_path=str(row.get("heading_path", "")),
            metadata=metadata if isinstance(metadata, dict) else {},
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

    @staticmethod
    def _build_where(filters: dict[str, Any] | None) -> str | None:
        if not filters:
            return None
        clauses: list[str] = []
        for key, value in filters.items():
            if key not in _FILTER_KEYS:
                continue
            if isinstance(value, (list, tuple, set)):
                values = [LanceVectorStore._escape(str(item)) for item in value]
                if values:
                    joined = ", ".join(f"'{v}'" for v in values)
                    clauses.append(f"{key} IN ({joined})")
            else:
                clauses.append(f"{key} = '{LanceVectorStore._escape(str(value))}'")
        return " AND ".join(clauses) if clauses else None

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "''")

    def _read_fingerprint(self) -> str | None:
        if not self._fingerprint_path.exists():
            return None
        try:
            data = json.loads(self._fingerprint_path.read_text(encoding="utf-8"))
            return data.get("fingerprint")
        except (json.JSONDecodeError, OSError):
            return None

    def _write_fingerprint(self, fingerprint: str) -> None:
        self._fingerprint_path.write_text(
            json.dumps({"fingerprint": fingerprint}), encoding="utf-8"
        )
