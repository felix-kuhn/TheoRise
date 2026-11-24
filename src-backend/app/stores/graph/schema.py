"""Canonical graph schema shared by the Ladybug and in-memory stores.

Ladybug (a Kuzu fork) requires every relationship table to declare a fixed
FROM/TO node pair, so each logical relationship is expanded into one concrete
rel table per source/target combination.
"""
from __future__ import annotations

NODE_LABELS: tuple[str, ...] = (
    "Theory",
    "Claim",
    "Construct",
    "Article",
    "Finding",
    "Document",
    "Community",
)

# (rel name, source label, target label)
REL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("ASSERTS", "Theory", "Claim"),
    ("ASSERTS_FINDING", "Document", "Finding"),
    ("MENTIONS", "Claim", "Construct"),
    ("MENTIONS_FINDING", "Finding", "Construct"),
    ("INFLUENCES", "Construct", "Construct"),
    ("MODERATES", "Construct", "Construct"),
    ("MEDIATES", "Construct", "Construct"),
    ("HAS_COMPONENT", "Theory", "Construct"),
    ("EXTENDS", "Theory", "Theory"),
    ("DERIVED_FROM", "Theory", "Theory"),
    ("CONTRASTS_WITH", "Theory", "Theory"),
    ("SUPPORTS", "Finding", "Claim"),
    ("CONTRADICTS", "Finding", "Claim"),
    ("REFINES", "Finding", "Claim"),
    ("INSTANTIATES", "Finding", "Claim"),
    ("EXTENDS", "Finding", "Claim"),
    ("SUPPORTS", "Finding", "Theory"),
    ("CONTRADICTS", "Finding", "Theory"),
    ("REFINES", "Finding", "Theory"),
    ("INSTANTIATES", "Finding", "Theory"),
    ("EXTENDS", "Finding", "Theory"),
    ("SUPPORTS", "Finding", "Construct"),
    ("CONTRADICTS", "Finding", "Construct"),
    ("REFINES", "Finding", "Construct"),
    ("INSTANTIATES", "Finding", "Construct"),
    ("EXTENDS", "Finding", "Construct"),
)


def rel_table_name(rel: str, source_label: str, target_label: str) -> str:
    """Return the concrete rel table name for a logical relationship."""
    return f"{rel}_{source_label}_{target_label}"


def node_ddl(label: str) -> str:
    return (
        f"CREATE NODE TABLE IF NOT EXISTS {label}("
        "id STRING PRIMARY KEY, name STRING, doc_id STRING, props STRING)"
    )


def rel_ddl(rel: str, source_label: str, target_label: str) -> str:
    table = rel_table_name(rel, source_label, target_label)
    return (
        f"CREATE REL TABLE IF NOT EXISTS {table}"
        f"(FROM {source_label} TO {target_label}, props STRING, edge_id STRING, "
        "rel_name STRING)"
    )


def graph_ddl() -> list[str]:
    """Return the ordered DDL statements for the whole graph schema."""
    statements = [node_ddl(label) for label in NODE_LABELS]
    statements.extend(rel_ddl(rel, src, dst) for rel, src, dst in REL_SPECS)
    return statements
