"""Storage interfaces shared by every store implementation.

Concrete implementations (SQLite, LanceDB, LadybugDB, in-memory fakes) plug
in behind these protocols so pipelines never depend on a specific engine.
(see docs/plan/03_storage_layer.md)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np


class IndexStaleError(RuntimeError):
    """Raised when a derived index no longer matches the source of truth."""


class GraphStoreError(RuntimeError):
    """Raised for invalid or unsupported graph operations."""


@dataclass
class VectorRow:
    """One row written into a vector store."""

    id: str
    vector: np.ndarray | list[float]
    text: str
    doc_id: str
    source_group: str = "A"
    kind: str = "chunk"
    heading_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hit:
    """One ranked search result."""

    id: str
    score: float
    text: str
    doc_id: str
    source_group: str = "A"
    kind: str = "chunk"
    heading_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Subgraph:
    """A bounded slice of the graph returned by ``neighbors``."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class VectorStore(Protocol):
    """Dense vector + lexical search over document chunks."""

    def ensure(self, dim: int, fingerprint: str) -> None: ...

    def upsert(self, rows: list[VectorRow]) -> None: ...

    def delete_by_doc(self, doc_id: str) -> None: ...

    def search_dense(
        self, vec: list[float], k: int, filters: dict[str, Any] | None = None
    ) -> list[Hit]: ...

    def search_fts(
        self, query: str, k: int, filters: dict[str, Any] | None = None
    ) -> list[Hit]: ...

    def search_hybrid(
        self,
        vec: list[float],
        query: str,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]: ...

    def count(self) -> int: ...

    def drop(self) -> None: ...


@runtime_checkable
class GraphStore(Protocol):
    """Property graph of theories, claims, findings, constructs and links."""

    def init_schema(self) -> None: ...

    def upsert_node(self, label: str, id: str, props: dict[str, Any]) -> None: ...

    def upsert_edge(
        self,
        rel: str,
        src: tuple[str, str],
        dst: tuple[str, str],
        props: dict[str, Any],
    ) -> None: ...

    def delete_by_doc(self, doc_id: str) -> None: ...

    def neighbors(
        self,
        node_id: str,
        depth: int = 1,
        rel_filter: list[str] | None = None,
        node_filter: list[str] | None = None,
        limit: int = 50,
    ) -> Subgraph: ...

    def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    def get_edge(self, edge_id: str) -> dict[str, Any] | None: ...

    def search_nodes(self, query: str, limit: int = 20) -> list[dict[str, Any]]: ...

    def shortest_path(self, a: str, b: str) -> list[dict[str, Any]] | None: ...

    def query_readonly(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...
