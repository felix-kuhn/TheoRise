"""Logging helpers with secret redaction."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(authorization\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
)


class RedactingFilter(logging.Filter):
    """Replaces obvious secrets in log records before they are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _SECRET_PATTERNS:
            message = pattern.sub(r"\1***", message)
        record.msg = message
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(
    data_dir: str | Path | None = None,
    level: int = logging.INFO,
) -> None:
    """Configure console logging and a JSON file log under ``data_dir``."""
    root = logging.getLogger()
    root.setLevel(level)

    if not any(getattr(handler, "_poc_console", False) for handler in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        console._poc_console = True  # type: ignore[attr-defined]
        root.addHandler(console)

    if data_dir is not None:
        logs_dir = Path(data_dir).expanduser() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        if not any(
            getattr(handler, "_poc_file", False) for handler in root.handlers
        ):
            file_handler = logging.FileHandler(
                logs_dir / "app.log",
                encoding="utf-8",
            )
            file_handler.setFormatter(JsonFormatter())
            file_handler._poc_file = True  # type: ignore[attr-defined]
            root.addHandler(file_handler)

    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
