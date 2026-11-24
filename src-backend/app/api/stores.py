"""Storage status endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import AppContext, get_context

router = APIRouter()


@router.get("/status")
def stores_status(ctx: AppContext = Depends(get_context)) -> dict:
    """Report store counts, fingerprint and schema versions."""
    vector_count = ctx.vector_store.count()
    return {
        "backend": {
            "vector": type(ctx.vector_store).__name__,
            "graph": type(ctx.graph_store).__name__,
        },
        "vector": {
            "count": vector_count,
            "dimensions": ctx.vector_dimensions,
            "fingerprint": ctx.vector_fingerprint,
        },
        "graph": ctx.graph_store.stats(),
        "schema_versions": ctx.schema_versions(),
    }
