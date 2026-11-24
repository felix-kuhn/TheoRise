"""Application context and FastAPI dependency wiring."""
from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Request

from .config import default_data_dir, load_config
from .gateway.gateway import Gateway
from .jobs.queue import JobRegistry
from .services.config import ConfigService


class AppContext:
    """Owns all long-lived state for one running instance."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        auth_token: str | None = None,
    ):
        self.data_dir = Path(data_dir or default_data_dir()).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.theories_dir = self.data_dir / "theories"
        self.index_path = self.data_dir / "theories_index.json"
        self.cfg = load_config(self.data_dir)
        self.config_service = ConfigService(self.data_dir)
        self.gateway = Gateway(self.config_service)
        self.jobs = JobRegistry()
        self.auth_token = auth_token or secrets.token_urlsafe(32)
        # file path -> (mtime, token count); recomputed when the file changes
        self._token_cache: dict[Path, tuple[float, int]] = {}

    def invalidate_token_cache(self) -> None:
        self._token_cache.clear()

    # --- metadata index (titles + source URLs per saved file) -------------------

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"runs": []}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and "runs" in data else {"runs": []}
        except (json.JSONDecodeError, OSError):
            return {"runs": []}

    def record_hydration(self, timestamp: str, files: list[dict]) -> None:
        """Store one hydration run (kept for versioning/audit)."""
        index = self._load_index()
        index["runs"].append(
            {
                "timestamp": timestamp,
                "at": datetime.now(UTC).isoformat(),
                "files": files,
            }
        )
        # keep the index small: last 20 runs are enough for the PoC
        index["runs"] = index["runs"][-20:]
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def theory_meta(self, slug: str, file: str) -> dict | None:
        """{title, url} recorded for this (slug, file), if any."""
        for run in reversed(self._load_index()["runs"]):
            if run.get("timestamp") not in file:
                continue
            for f in run.get("files", []):
                if f.get("slug") == slug and f.get("file") == file:
                    return {"title": f.get("title"), "url": f.get("url")}
        return None


def get_context(request: Request) -> AppContext:
    """FastAPI dependency resolving the app's shared context."""
    return request.app.state.ctx


def get_config_service(request: Request) -> ConfigService:
    return request.app.state.ctx.config_service


def get_gateway(request: Request) -> Gateway:
    return request.app.state.ctx.gateway
