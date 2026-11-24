"""Contract tests for every GraphStore implementation."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.stores.graph.in_memory import InMemoryGraphStore
from app.stores.graph.ladybug import LadybugGraphStore
from app.stores.interfaces import GraphStore, GraphStoreError


@pytest.fixture(params=["inmemory", "ladybug"])
def graph_store(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[GraphStore, bool]:
    if request.param == "inmemory":
        return InMemoryGraphStore(), False
    return LadybugGraphStore(tmp_path), True


def _build(store: GraphStore) -> None:
    store.init_schema()
    store.upsert_node("Theory", "t1", {"name": "Theory One", "doc_id": "d1"})
    store.upsert_node("Claim", "c1", {"name": "Claim One", "doc_id": "d1"})
    store.upsert_node("Construct", "x1", {"name": "Construct One", "doc_id": ""})
    store.upsert_node("Finding", "f1", {"name": "Finding One", "doc_id": "d1"})
    store.upsert_edge(
        "ASSERTS",
        ("t1", "Theory"),
        ("c1", "Claim"),
        {"edge_id": "e1", "confidence": 0.9},
    )
    store.upsert_edge(
        "MENTIONS",
        ("c1", "Claim"),
        ("x1", "Construct"),
        {"edge_id": "e2"},
    )
    store.upsert_edge(
        "SUPPORTS",
        ("f1", "Finding"),
        ("c1", "Claim"),
        {"edge_id": "e3"},
    )


def test_node_and_edge_roundtrip(graph_store: tuple[GraphStore, bool]) -> None:
    store, _ = graph_store
    _build(store)

    node = store.get_node("t1")
    assert node is not None
    assert node["id"] == "t1"
    assert node["label"] == "Theory"
    assert node["name"] == "Theory One"

    edge = store.get_edge("e1")
    assert edge is not None
    assert edge["rel"] == "ASSERTS"
    assert edge["source"] == "t1"
    assert edge["target"] == "c1"


def test_upsert_is_idempotent(graph_store: tuple[GraphStore, bool]) -> None:
    store, _ = graph_store
    _build(store)
    stats_before = store.stats()

    store.upsert_node("Theory", "t1", {"name": "Theory One", "doc_id": "d1"})
    store.upsert_edge(
        "ASSERTS",
        ("t1", "Theory"),
        ("c1", "Claim"),
        {"edge_id": "e1", "confidence": 0.95},
    )
    stats_after = store.stats()

    assert stats_after["node_count"] == stats_before["node_count"]
    assert stats_after["edge_count"] == stats_before["edge_count"]


def test_delete_by_doc(graph_store: tuple[GraphStore, bool]) -> None:
    store, _ = graph_store
    _build(store)

    store.delete_by_doc("d1")

    assert store.get_node("t1") is None
    assert store.get_node("c1") is None
    assert store.get_node("x1") is not None


def test_neighbors_depth_and_filters(graph_store: tuple[GraphStore, bool]) -> None:
    store, _ = graph_store
    _build(store)

    subgraph = store.neighbors("t1", depth=1)
    assert {node["id"] for node in subgraph.nodes} == {"t1", "c1"}

    subgraph2 = store.neighbors("t1", depth=2)
    assert {"x1", "f1"} <= {node["id"] for node in subgraph2.nodes}

    filtered = store.neighbors("t1", depth=2, rel_filter=["MENTIONS"])
    assert filtered.edges
    assert all(edge["rel"] == "MENTIONS" for edge in filtered.edges)

    node_filtered = store.neighbors("t1", depth=2, node_filter=["Theory"])
    assert {node["label"] for node in node_filtered.nodes} == {"Theory"}


def test_search_nodes(graph_store: tuple[GraphStore, bool]) -> None:
    store, _ = graph_store
    _build(store)

    results = store.search_nodes("Construct", limit=10)
    assert any(node["id"] == "x1" for node in results)


def test_shortest_path(graph_store: tuple[GraphStore, bool]) -> None:
    store, _ = graph_store
    _build(store)

    path = store.shortest_path("t1", "x1")
    assert path is not None
    assert [node["id"] for node in path] == ["t1", "c1", "x1"]

    assert store.shortest_path("t1", "missing") is None


def test_stats(graph_store: tuple[GraphStore, bool]) -> None:
    store, _ = graph_store
    _build(store)

    stats = store.stats()
    assert stats["node_count"] == 4
    assert stats["edge_count"] == 3


def test_readonly_guard(graph_store: tuple[GraphStore, bool]) -> None:
    store, supports_cypher = graph_store
    store.init_schema()

    if supports_cypher:
        result = store.query_readonly("MATCH (n) RETURN n")
        assert isinstance(result, list)
    else:
        with pytest.raises(GraphStoreError):
            store.query_readonly("MATCH (n) RETURN n")

    with pytest.raises(GraphStoreError):
        store.query_readonly("CREATE (n:Thing)")
