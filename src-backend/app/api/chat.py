"""Chat endpoint used by the frontend; all model calls stay in the backend."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..core.errors import AppError
from ..deps import get_gateway
from ..gateway.gateway import Gateway
from ..gateway.llm_client import GatewayError

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[dict[str, str]] = Field(min_length=1)
    role: Literal["chat"] = "chat"


@router.post("")
async def chat(
    payload: ChatRequest,
    gateway: Gateway = Depends(get_gateway),
) -> dict[str, str]:
    try:
        result = await gateway.chat(
            payload.messages,
            role=payload.role,
            use_cache=False,
        )
    except GatewayError as exc:
        raise AppError(
            502,
            "gateway_error",
            str(exc),
            details={"role": payload.role},
        ) from exc
    if not isinstance(result, str):
        raise AppError(502, "gateway_error", "Chat endpoint returned no text")
    return {"content": result}
