"""NetworkX-backed in-memory graph store for tests and fallback."""
from __future__ import annotations

from typing import Any

import networkx as nx

from ...core.ids import new_id
from ..interfaces import GraphStoreError, Subgraph


class InMemoryGraphStore:
    """A NetworkX MultiDiGraph implementation of :class:`GraphStore`."""

    def __init__(self) -> None:
        self._graph = nx.MultiDiGraph()

    def init_schema(self) -> None:
        return None

    def upsert_node(self, label: str, id: str, props: dict[str, Any]) -> None:
        self._graph.add_node(
            id,
            label=label,
            name=str(props.get("name", "")),
            doc_id=str(props.get("doc_id", "")),
            props=dict(props),
        )

    def upsert_edge(
        self,
        rel: str,
        src: tuple[str, str],
        dst: tuple[str, str],
        props: dict[str, Any],
    ) -> None:
        src_id, src_label = src
        dst_id, dst_label = dst
        edge_id = str(props.get("edge_id") or new_id("edge"))
        self._graph.add_edge(
            src_id,
            dst_id,
            key=edge_id,
            rel=rel,
            source_label=src_label,
            target_label=dst_label,
            props=dict(props),
        )

    def delete_by_doc(self, doc_id: str) -> None:
        stale = [
            node_id
            for node_id, data in self._graph.nodes(data=True)
            if data.get("doc_id") == doc_id
        ]
        for node_id in stale:
            self._graph.remove_node(node_id)

    def neighbors(
        self,
        node_id: str,
        depth: int = 1,
        rel_filter: list[str] | None = None,
        node_filter: list[str] | None = None,
        limit: int = 50,
    ) -> Subgraph:
        if node_id not in self._graph:
            return Subgraph(nodes=[], edges=[])

        depth = max(0, int(depth))
        rel_set = set(rel_filter or [])
        node_set = set(node_filter or [])
        undirected = self._graph.to_undirected()
        lengths = nx.single_source_shortest_path_length(undirected, node_id, cutoff=depth)
        frontier = set(lengths)

        nodes: dict[str, dict[str, Any]] = {}
        for nid in sorted(frontier):
            data = self._graph.nodes[nid]
            if node_set and data.get("label") not in node_set:
                continue
            nodes[nid] = self._node_dict(nid, data)

        edges: dict[str, dict[str, Any]] = {}
        for u, v, key, data in self._graph.edges(keys=True, data=True):
            if u not in frontier or v not in frontier:
                continue
            if rel_set and data.get("rel") not in rel_set:
                continue
            if node_set and (
                data.get("source_label") not in node_set
                or data.get("target_label") not in node_set
            ):
                continue
            edges[str(key)] = self._edge_dict(u, v, key, data)

        return Subgraph(
            nodes=list(nodes.values())[:limit],
            edges=list(edges.values())[:limit],
        )

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if node_id not in self._graph:
            return None
        return self._node_dict(node_id, self._graph.nodes[node_id])

    def get_edge(self, edge_id: str) -> dict[str, Any] | None:
        for u, v, key, data in self._graph.edges(keys=True, data=True):
            if str(key) == edge_id:
                return self._edge_dict(u, v, key, data)
        return None

    def search_nodes(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        needle = query.lower()
        results: list[dict[str, Any]] = []
        for nid, data in self._graph.nodes(data=True):
            name = str(data.get("name", "")).lower()
            if needle in name or needle in str(nid).lower():
                results.append(self._node_dict(nid, data))
                if len(results) >= limit:
                    break
        return results

    def shortest_path(self, a: str, b: str) -> list[dict[str, Any]] | None:
        if a not in self._graph or b not in self._graph:
            return None
        try:
            path = nx.shortest_path(self._graph.to_undirected(), a, b)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        return [self._node_dict(nid, self._graph.nodes[nid]) for nid in path]

    def query_readonly(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise GraphStoreError(
            "Cypher queries are not supported by the in-memory graph store"
        )

    def stats(self) -> dict[str, Any]:
        return {
            "node_count": self._graph.number_of_nodes(),
            "edge_count": self._graph.number_of_edges(),
            "table_count": 0,
            "tables": [],
        }

    @staticmethod
    def _node_dict(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(node_id),
            "label": str(data.get("label", "")),
            "name": str(data.get("name", "")),
            "doc_id": str(data.get("doc_id", "")),
            "props": dict(data.get("props", {})),
        }

    @staticmethod
    def _edge_dict(
        u: str, v: str, key: Any, data: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "id": str(key),
            "rel": str(data.get("rel", "")),
            "source": str(u),
            "target": str(v),
            "source_label": str(data.get("source_label", "")),
            "target_label": str(data.get("target_label", "")),
            "props": dict(data.get("props", {})),
        }
