"""LadybugDB-backed property graph store.

Ladybug is an embedded Kuzu fork. Every relationship table needs a fixed
FROM/TO node pair (see :mod:`app.stores.graph.schema`), so the store resolves
a logical relationship plus source/target labels into a concrete rel table.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from ...core.ids import new_id
from ..interfaces import GraphStoreError, Subgraph
from .schema import graph_ddl, rel_table_name

_WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DROP|COPY|INSERT|UPDATE|ALTER|ATTACH|DETACH)\b",
    re.IGNORECASE,
)
_CALL_RE = re.compile(r"\bCALL\b", re.IGNORECASE)
_SHOW_TABLES_RE = re.compile(r"\bSHOW_TABLES\b", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LadybugGraphStore:
    """A LadybugDB implementation of :class:`GraphStore`."""

    def __init__(self, data_dir: str | Path) -> None:
        import ladybug

        self._db_path = Path(data_dir) / "graph" / "graph.ladybug"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = ladybug.Database(str(self._db_path))
        self._conn = ladybug.Connection(self._db)

    def init_schema(self) -> None:
        for statement in graph_ddl():
            self._execute(statement)

    def upsert_node(self, label: str, id: str, props: dict[str, Any]) -> None:
        self._assert_identifier(label)
        name = str(props.get("name", ""))
        doc_id = str(props.get("doc_id", ""))
        payload = json.dumps(props, ensure_ascii=False)
        self._execute(
            (
                f"MERGE (n:{label} {{id:$id}}) "
                "SET n.name=$name, n.doc_id=$doc_id, n.props=$props "
                "RETURN n.id AS id"
            ),
            {"id": id, "name": name, "doc_id": doc_id, "props": payload},
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
        self._assert_identifier(src_label)
        self._assert_identifier(dst_label)
        table = rel_table_name(rel, src_label, dst_label)
        self._assert_identifier(table)
        edge_id = str(props.get("edge_id") or new_id("edge"))
        payload = json.dumps(props, ensure_ascii=False)
        self._execute(
            (
                f"MATCH (s:{src_label} {{id:$sid}}), (d:{dst_label} {{id:$did}}) "
                f"MERGE (s)-[r:{table}]->(d) "
                "SET r.props=$props, r.edge_id=$edge_id, r.rel_name=$rel_name "
                "RETURN r.edge_id AS edge_id"
            ),
            {
                "sid": src_id,
                "did": dst_id,
                "props": payload,
                "edge_id": edge_id,
                "rel_name": rel,
            },
        )

    def delete_by_doc(self, doc_id: str) -> None:
        self._execute(
            "MATCH (n) WHERE n.doc_id=$doc_id DETACH DELETE n",
            {"doc_id": doc_id},
        )

    def neighbors(
        self,
        node_id: str,
        depth: int = 1,
        rel_filter: list[str] | None = None,
        node_filter: list[str] | None = None,
        limit: int = 50,
    ) -> Subgraph:
        depth = max(0, int(depth))
        rel_set = set(rel_filter or [])
        node_set = set(node_filter or [])

        node_rows = self._execute(
            f"MATCH (n)-[*0..{depth}]-(m) WHERE n.id=$id RETURN DISTINCT m",
            {"id": node_id},
        )
        nodes: dict[str, dict[str, Any]] = {}
        for row in node_rows:
            node = self._node_dict(row["m"])
            if node_set and node["label"] not in node_set:
                continue
            nodes[node["id"]] = node

        start_node = self.get_node(node_id)
        if start_node is not None:
            nodes.setdefault(start_node["id"], start_node)

        if not nodes:
            return Subgraph(nodes=[], edges=[])

        ids = list(nodes)
        edge_rows = self._execute(
            "MATCH (a)-[r]-(b) WHERE a.id IN $ids AND b.id IN $ids RETURN a, r, b",
            {"ids": ids},
        )
        edges: dict[str, dict[str, Any]] = {}
        for row in edge_rows:
            edge = self._edge_dict(row["a"], row["r"], row["b"])
            if rel_set and edge["rel"] not in rel_set:
                continue
            if node_set and (
                edge["source_label"] not in node_set
                or edge["target_label"] not in node_set
            ):
                continue
            edges.setdefault(edge["id"], edge)

        return Subgraph(
            nodes=list(nodes.values())[:limit],
            edges=list(edges.values())[:limit],
        )

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        rows = self._execute("MATCH (n) WHERE n.id=$id RETURN n", {"id": node_id})
        if not rows:
            return None
        return self._node_dict(rows[0]["n"])

    def get_edge(self, edge_id: str) -> dict[str, Any] | None:
        rows = self._execute(
            "MATCH (a)-[r]->(b) WHERE r.edge_id=$id RETURN a, r, b",
            {"id": edge_id},
        )
        if not rows:
            return None
        return self._edge_dict(rows[0]["a"], rows[0]["r"], rows[0]["b"])

    def search_nodes(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._execute(
            "MATCH (n) WHERE n.name CONTAINS $q OR n.id CONTAINS $q "
            "RETURN n LIMIT $limit",
            {"q": query, "limit": limit},
        )
        return [self._node_dict(row["n"]) for row in rows]

    def shortest_path(self, a: str, b: str) -> list[dict[str, Any]] | None:
        if a == b:
            node = self.get_node(a)
            return [node] if node else None
        rows = self._execute(
            "MATCH p = (a)-[*SHORTEST]-(b) WHERE a.id=$a AND b.id=$b RETURN p",
            {"a": a, "b": b},
        )
        if not rows:
            return None
        path = rows[0]["p"]
        return [self._node_dict(node) for node in path.get("_NODES", [])]

    def query_readonly(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self._assert_readonly(cypher)
        return self._execute(cypher, params or {})

    def stats(self) -> dict[str, Any]:
        tables = self._execute("CALL show_tables() RETURN *")
        node_count_rows = self._execute("MATCH (n) RETURN count(n) AS c")
        edge_count_rows = self._execute("MATCH ()-[r]->() RETURN count(r) AS c")
        return {
            "node_count": int(node_count_rows[0]["c"]) if node_count_rows else 0,
            "edge_count": int(edge_count_rows[0]["c"]) if edge_count_rows else 0,
            "table_count": len(tables),
            "tables": [row.get("name") for row in tables],
        }

    @staticmethod
    def _node_dict(node: dict[str, Any]) -> dict[str, Any]:
        props = _parse_json(node.get("props"))
        return {
            "id": str(node.get("id", "")),
            "label": str(node.get("_LABEL", "")),
            "name": str(node.get("name", "")),
            "doc_id": str(node.get("doc_id") or ""),
            "props": props,
        }

    @staticmethod
    def _edge_dict(
        a: dict[str, Any], rel: dict[str, Any], b: dict[str, Any]
    ) -> dict[str, Any]:
        if rel.get("_SRC") == a.get("_ID"):
            source, target = a, b
        else:
            source, target = b, a
        props = _parse_json(rel.get("props"))
        return {
            "id": str(rel.get("edge_id", "")),
            "rel": str(rel.get("rel_name") or rel.get("_LABEL", "")),
            "source": str(source.get("id", "")),
            "target": str(target.get("id", "")),
            "source_label": str(source.get("_LABEL", "")),
            "target_label": str(target.get("_LABEL", "")),
            "props": props,
        }

    @staticmethod
    def _assert_readonly(cypher: str) -> None:
        if _WRITE_RE.search(cypher):
            raise GraphStoreError("Graph query is not read-only")
        if _CALL_RE.search(cypher) and not _SHOW_TABLES_RE.search(cypher):
            raise GraphStoreError("Graph CALL is not read-only")

    @staticmethod
    def _assert_identifier(name: str) -> None:
        if not _IDENTIFIER_RE.match(name):
            raise GraphStoreError(f"Invalid graph identifier: {name!r}")

    def _execute(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        try:
            result = self._conn.execute(cypher, params or {})
            rows = cast(Any, result).rows_as_dict().get_all()
            return cast(list[dict[str, Any]], rows)
        except GraphStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalized for callers
            raise GraphStoreError(f"Graph query failed: {exc}") from exc


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
