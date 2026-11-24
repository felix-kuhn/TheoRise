"""Runtime configuration endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from pydantic import ValidationError

from ..core.errors import AppError
from ..deps import get_config_service, get_gateway
from ..gateway.gateway import Gateway
from ..schemas.config import ROLE_NAMES
from ..services.config import ConfigService

router = APIRouter()


@router.get("")
async def get_config(
    service: ConfigService = Depends(get_config_service),
) -> dict:
    return service.public_config()


@router.put("")
async def put_config(
    payload: dict = Body(...),
    service: ConfigService = Depends(get_config_service),
) -> dict:
    try:
        service.save(payload)
    except ValidationError as exc:
        raise AppError(
            422,
            "validation_error",
            "Request validation failed",
            details={"errors": exc.errors()},
        ) from exc
    return service.public_config()


@router.post("/test")
async def test_config(
    payload: dict | None = Body(default=None),
    gateway: Gateway = Depends(get_gateway),
) -> dict:
    role = (payload or {}).get("role")
    if role is not None:
        if role not in ROLE_NAMES:
            raise AppError(422, "validation_error", details={"role": role})
        return await gateway.test_role(role)
    results = []
    for role_name in ROLE_NAMES:
        results.append(await gateway.test_role(role_name))
    return {"results": results}


@router.get("/models")
async def list_models(
    role: str = Query(...),
    gateway: Gateway = Depends(get_gateway),
) -> dict:
    if role not in ROLE_NAMES:
        raise AppError(422, "validation_error", details={"role": role})
    try:
        models = await gateway.list_models(role)
    except Exception as exc:  # noqa: BLE001 - normalized for the UI
        raise AppError(
            502,
            "gateway_error",
            "Could not list models",
            details={"role": role, "error": str(exc)[:300]},
        ) from exc
    return {"role": role, "models": models}


@router.get("/network-status")
async def network_status(
    gateway: Gateway = Depends(get_gateway),
) -> dict:
    return {"roles": gateway.network_status()}
