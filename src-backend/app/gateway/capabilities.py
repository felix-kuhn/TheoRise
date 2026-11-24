"""Capability probes and offline hints."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from ..schemas.config import ROLE_NAMES, AppConfig


def is_local_host(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def network_status(config: AppConfig) -> list[dict]:
    results: list[dict] = []
    for role in ROLE_NAMES:
        role_config = getattr(config, role)
        base_url = getattr(role_config, "base_url", None)
        if base_url is None:
            results.append({"role": role, "base_url": None, "local": True})
            continue
        url = str(base_url)
        results.append(
            {
                "role": role,
                "base_url": url,
                "host": urlparse(url).hostname or "",
                "local": is_local_host(url),
            }
        )
    return results
