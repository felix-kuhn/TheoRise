"""Contract tests for every VectorStore implementation."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from app.stores.interfaces import IndexStaleError, VectorRow, VectorStore
from app.stores.vector.in_memory import InMemoryVectorStore
from app.stores.vector.lance import LanceVectorStore

DIM = 64


def _row(
    i: int,
    *,
    doc_id: str = "d1",
    group: str = "A",
    kind: str = "chunk",
    text: str = "",
    heading: str = "",
    metadata: dict | None = None,
) -> VectorRow:
    vec = np.zeros(DIM, dtype=np.float32)
    vec[i % DIM] = 1.0
    return VectorRow(
        id=f"row{i}",
        vector=vec,
        text=text or f"sample text {i}",
        doc_id=doc_id,
        source_group=group,
        kind=kind,
        heading_path=heading,
        metadata=metadata or {},
    )


@pytest.fixture(params=["inmemory", "lance"])
def factory(request: pytest.FixtureRequest, tmp_path: Path) -> Callable[[], VectorStore]:
    if request.param == "inmemory":
        return InMemoryVectorStore
    return lambda: LanceVectorStore(
        tmp_path,
        fts_index_min_rows=1,
        ann_index_threshold=10**9,
    )


def test_upsert_and_count(factory: Callable[[], VectorStore]) -> None:
    store = factory()
    store.ensure(DIM, "fp")
    store.upsert([_row(0), _row(1), _row(2, doc_id="d2")])
    assert store.count() == 3


def test_upsert_is_idempotent(factory: Callable[[], VectorStore]) -> None:
    store = factory()
    store.ensure(DIM, "fp")
    store.upsert([_row(0), _row(1)])
    store.upsert([_row(0, text="updated text")])
    assert store.count() == 2
    hits = store.search_dense(_row(0).vector, k=5)
    assert any(hit.id == "row0" and hit.text == "updated text" for hit in hits)


def test_delete_by_doc(factory: Callable[[], VectorStore]) -> None:
    store = factory()
    store.ensure(DIM, "fp")
    store.upsert([_row(0, doc_id="d1"), _row(1, doc_id="d2"), _row(2, doc_id="d1")])
    store.delete_by_doc("d1")
    assert store.count() == 1
    hits = store.search_dense(_row(0).vector, k=10)
    assert all(hit.doc_id == "d2" for hit in hits)


def test_search_dense_ranks_closest_first(factory: Callable[[], VectorStore]) -> None:
    store = factory()
    store.ensure(DIM, "fp")
    store.upsert([_row(0), _row(1), _row(2)])
    hits = store.search_dense(_row(0).vector, k=3)
    assert hits[0].id == "row0"
    assert hits[0].score >= hits[1].score


def test_search_fts_and_hybrid(factory: Callable[[], VectorStore]) -> None:
    store = factory()
    store.ensure(DIM, "fp")
    store.upsert(
        [
            _row(0, text="the quick brown fox jumps"),
            _row(1, text="lazy dogs sleep"),
            _row(2, text="foxes are clever"),
        ]
    )

    fts = store.search_fts("fox", k=3)
    assert any(hit.id == "row0" for hit in fts)

    hybrid = store.search_hybrid(_row(2).vector, "fox", k=3)
    assert hybrid
    assert all(hasattr(hit, "score") for hit in hybrid)


def test_filters(factory: Callable[[], VectorStore]) -> None:
    store = factory()
    store.ensure(DIM, "fp")
    store.upsert(
        [
            _row(0, doc_id="d1", group="A"),
            _row(1, doc_id="d2", group="B"),
            _row(2, doc_id="d1", group="A"),
        ]
    )

    hits = store.search_dense(_row(0).vector, k=10, filters={"doc_id": "d1"})
    assert hits and all(hit.doc_id == "d1" for hit in hits)

    fts = store.search_fts("sample", k=10, filters={"source_group": "B"})
    assert fts and all(hit.source_group == "B" for hit in fts)


def test_fingerprint_and_dimension_mismatch_raise(
    factory: Callable[[], VectorStore],
) -> None:
    store = factory()
    store.ensure(DIM, "fp1")

    with pytest.raises(IndexStaleError):
        store.ensure(DIM, "fp2")

    with pytest.raises(IndexStaleError):
        store.ensure(32, "fp1")


def test_drop_clears_data(factory: Callable[[], VectorStore]) -> None:
    store = factory()
    store.ensure(DIM, "fp")
    store.upsert([_row(0), _row(1)])
    store.drop()
    assert store.count() == 0
