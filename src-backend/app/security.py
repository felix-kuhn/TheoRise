"""Request authentication for the local API."""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Dependency applied to every route; rejects requests without the token."""
    token = request.app.state.ctx.auth_token
    expected = f"Bearer {token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": "Missing or invalid bearer token",
            },
        )
