"""Rebuild the derived vector and graph stores from the SQLite truth store.

Pipelines will call these after ingestion/extraction. For now they read
whatever tables exist and repopulate the stores idempotently.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from .interfaces import GraphStore, VectorRow, VectorStore
from .sqlite.database import SqliteDatabase


def rebuild_vectors(
    db: SqliteDatabase,
    vector_store: VectorStore,
    embed: Callable[[Sequence[str]], Any],
    *,
    dim: int,
    fingerprint: str,
) -> int:
    """Re-index chunks, claims and findings from SQLite into ``vector_store``."""
    rows = _read_vector_rows(db)
    vector_store.drop()
    vector_store.ensure(dim, fingerprint)
    if not rows:
        return 0

    vectors = embed([row.text for row in rows])
    matrix = _as_matrix(vectors)
    if matrix.shape[0] != len(rows):
        raise ValueError("embedder returned the wrong number of vectors")
    if matrix.shape[1] != dim:
        raise ValueError(
            f"embedder returned dimension {matrix.shape[1]} but expected {dim}"
        )

    for row, vector in zip(rows, matrix, strict=True):
        row.vector = vector.tolist()
    vector_store.upsert(rows)
    return len(rows)


def rebuild_graph(db: SqliteDatabase, graph_store: GraphStore) -> int:
    """Rebuild graph nodes and edges from the SQLite truth store."""
    graph_store.init_schema()
    _upsert_theories(db, graph_store)
    _upsert_claims(db, graph_store)
    _upsert_findings(db, graph_store)
    _upsert_constructs(db, graph_store)
    _upsert_documents(db, graph_store)
    _upsert_links(db, graph_store)
    return graph_store.stats().get("node_count", 0)


def _read_vector_rows(db: SqliteDatabase) -> list[VectorRow]:
    rows: list[VectorRow] = []
    with db.connect() as conn:
        for row in conn.execute(
            """
            SELECT c.chunk_id AS id, c.doc_id, c.text, c.heading_path, c.kind,
                   c.metadata_json, COALESCE(d.source_group, 'A') AS source_group
            FROM chunks c LEFT JOIN documents d ON d.doc_id = c.doc_id
            """
        ):
            rows.append(
                VectorRow(
                    id=str(row["id"]),
                    vector=[],
                    text=str(row["text"]),
                    doc_id=str(row["doc_id"]),
                    source_group=str(row["source_group"]),
                    kind=str(row["kind"] or "chunk"),
                    heading_path=str(row["heading_path"] or ""),
                    metadata=_json_dict(row["metadata_json"]),
                )
            )
        for row in conn.execute(
            """
            SELECT f.finding_id AS id, f.doc_id, f.text, 'finding' AS kind,
                   '{}' AS metadata_json, COALESCE(d.source_group, 'B') AS source_group
            FROM findings f LEFT JOIN documents d ON d.doc_id = f.doc_id
            """
        ):
            rows.append(
                VectorRow(
                    id=str(row["id"]),
                    vector=[],
                    text=str(row["text"]),
                    doc_id=str(row["doc_id"]),
                    source_group=str(row["source_group"]),
                    kind=str(row["kind"]),
                    heading_path="",
                    metadata={},
                )
            )
    return rows


def _upsert_theories(db: SqliteDatabase, graph_store: GraphStore) -> None:
    with db.connect() as conn:
        for row in conn.execute(
            """
            SELECT doc_id, name, acronym, aliases_json, originating_area,
                   gregor_type, card_json
            FROM theories
            """
        ):
            graph_store.upsert_node(
                "Theory",
                _node_id("theory", row["doc_id"]),
                {
                    "name": str(row["name"]),
                    "doc_id": str(row["doc_id"]),
                    "acronym": _none_to_str(row["acronym"]),
                    "aliases": _json_list(row["aliases_json"]),
                    "originating_area": _none_to_str(row["originating_area"]),
                    "gregor_type": _none_to_str(row["gregor_type"]),
                    "card": _json_dict(row["card_json"]),
                },
            )


def _upsert_claims(db: SqliteDatabase, graph_store: GraphStore) -> None:
    with db.connect() as conn:
        for row in conn.execute(
            """
            SELECT claim_id, doc_id, chunk_id, text, kind, constructs_json,
                   polarity, confidence, model, prompt_version
            FROM claims
            """
        ):
            graph_store.upsert_node(
                "Claim",
                _node_id("claim", row["claim_id"]),
                {
                    "name": str(row["text"])[:200],
                    "doc_id": str(row["doc_id"]),
                    "text": str(row["text"]),
                    "chunk_id": _none_to_str(row["chunk_id"]),
                    "kind": str(row["kind"]),
                    "constructs": _json_list(row["constructs_json"]),
                    "polarity": str(row["polarity"]),
                    "confidence": _none_to_float(row["confidence"]),
                    "model": str(row["model"]),
                    "prompt_version": str(row["prompt_version"]),
                },
            )


def _upsert_findings(db: SqliteDatabase, graph_store: GraphStore) -> None:
    with db.connect() as conn:
        for row in conn.execute(
            """
            SELECT finding_id, doc_id, chunk_id, text, kind, constructs_json,
                   polarity, evidence_span, confidence, model, prompt_version
            FROM findings
            """
        ):
            graph_store.upsert_node(
                "Finding",
                _node_id("finding", row["finding_id"]),
                {
                    "name": str(row["text"])[:200],
                    "doc_id": str(row["doc_id"]),
                    "text": str(row["text"]),
                    "chunk_id": _none_to_str(row["chunk_id"]),
                    "kind": str(row["kind"]),
                    "constructs": _json_list(row["constructs_json"]),
                    "polarity": str(row["polarity"]),
                    "evidence_span": str(row["evidence_span"]),
                    "confidence": _none_to_float(row["confidence"]),
                    "model": str(row["model"]),
                    "prompt_version": str(row["prompt_version"]),
                },
            )


def _upsert_constructs(db: SqliteDatabase, graph_store: GraphStore) -> None:
    with db.connect() as conn:
        for row in conn.execute(
            """
            SELECT construct_id, canonical_name, aliases_json, description, created_by
            FROM constructs
            """
        ):
            graph_store.upsert_node(
                "Construct",
                _node_id("construct", row["construct_id"]),
                {
                    "name": str(row["canonical_name"]),
                    "doc_id": "",
                    "aliases": _json_list(row["aliases_json"]),
                    "description": _none_to_str(row["description"]),
                    "created_by": str(row["created_by"]),
                },
            )


def _upsert_documents(db: SqliteDatabase, graph_store: GraphStore) -> None:
    with db.connect() as conn:
        for row in conn.execute(
            """
            SELECT doc_id, source_group, doc_type, title, status, metadata_json
            FROM documents
            """
        ):
            graph_store.upsert_node(
                "Document",
                _node_id("document", row["doc_id"]),
                {
                    "name": str(row["title"]),
                    "doc_id": str(row["doc_id"]),
                    "source_group": str(row["source_group"]),
                    "doc_type": str(row["doc_type"]),
                    "status": str(row["status"]),
                    "metadata": _json_dict(row["metadata_json"]),
                },
            )


def _upsert_links(db: SqliteDatabase, graph_store: GraphStore) -> None:
    with db.connect() as conn:
        for row in conn.execute(
            """
            SELECT link_id, source_type, source_id, target_type, target_id,
                   label, confidence, rationale, source_evidence, target_evidence,
                   status, model, prompt_version
            FROM links
            """
        ):
            source_label = _label_for(row["source_type"])
            target_label = _label_for(row["target_type"])
            graph_store.upsert_edge(
                str(row["label"]),
                (_node_id(row["source_type"], row["source_id"]), source_label),
                (_node_id(row["target_type"], row["target_id"]), target_label),
                {
                    "edge_id": str(row["link_id"]),
                    "confidence": _none_to_float(row["confidence"]),
                    "rationale": str(row["rationale"]),
                    "source_evidence": str(row["source_evidence"]),
                    "target_evidence": str(row["target_evidence"]),
                    "status": str(row["status"]),
                    "model": str(row["model"]),
                    "prompt_version": str(row["prompt_version"]),
                },
            )


def _node_id(kind: str, entity_id: Any) -> str:
    return f"{kind}:{entity_id}"


def _label_for(kind: str) -> str:
    return {
        "theory": "Theory",
        "claim": "Claim",
        "finding": "Finding",
        "construct": "Construct",
        "document": "Document",
        "article": "Article",
        "community": "Community",
    }.get(str(kind).lower(), str(kind).capitalize())


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _none_to_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _none_to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _as_matrix(vectors: Any) -> Any:
    import numpy as np

    return np.asarray(vectors, dtype=np.float32)
