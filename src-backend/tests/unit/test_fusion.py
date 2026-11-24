"""Unit tests for reciprocal rank fusion."""
from __future__ import annotations

from app.pipelines.retrieval.fusion import fuse


def test_fuse_interleaves_rankings_by_reciprocal_rank() -> None:
    first = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    second = [{"id": "b"}, {"id": "c"}, {"id": "d"}]

    result = fuse([first, second], k=60)

    assert [item["id"] for item in result] == ["b", "c", "a", "d"]
    assert result[0]["score"] > result[1]["score"]
    assert result[1]["score"] > result[2]["score"]


def test_fuse_handles_empty_and_missing_ids() -> None:
    assert fuse([[], []], k=10) == []

    result = fuse([[{"id": "x"}], []], k=10)
    assert result == [{"id": "x", "score": 1.0 / 11.0}]


def test_fuse_annotates_score_without_mutating_input() -> None:
    ranking = [{"id": "a"}]
    result = fuse([ranking], k=60)

    assert result[0]["score"] > 0
    assert ranking[0] == {"id": "a"}
