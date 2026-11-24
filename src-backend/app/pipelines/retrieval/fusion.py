"""Reciprocal Rank Fusion over multiple rankings (pure, unit-tested)."""
from __future__ import annotations

from typing import Any


def fuse(rankings: list[list[dict[str, Any]]], k: int = 60) -> list[dict[str, Any]]:
    """Fuse ranked item lists using reciprocal rank fusion.

    Each item is a dict carrying an ``id`` key. The returned items are ordered
    by descending fused score and annotated with a ``score`` field.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            item_id = str(item["id"])
            if item_id not in items:
                items[item_id] = item
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)

    ordered = sorted(items, key=lambda item_id: scores[item_id], reverse=True)
    return [{**items[item_id], "score": scores[item_id]} for item_id in ordered]
