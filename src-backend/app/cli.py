"""CLI entry point: ``python -m app --port 0 --token <T> --data-dir <path>``."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import uvicorn

from .config import default_data_dir
from .main import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="Run the theories backend as a local sidecar.",
    )
    parser.add_argument("--port", type=int, default=0, help="Port to bind (0 = free port)")
    parser.add_argument("--token", default=None, help="Bearer token required by the API")
    parser.add_argument("--data-dir", default=None, help="Directory for runtime data")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = args.token or os.environ.get("APP_AUTH_TOKEN")
    if not token:
        print("error: --token is required (or set APP_AUTH_TOKEN)", file=sys.stderr)
        return 2

    data_dir = Path(args.data_dir or default_data_dir()).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["APP_AUTH_TOKEN"] = token

    config = uvicorn.Config(
        create_app(str(data_dir), auth_token=token),
        host="127.0.0.1",
        port=args.port,
        log_config=None,
        access_log=False,
        workers=1,
    )
    sock = config.bind_socket()
    port = int(sock.getsockname()[1])
    print(json.dumps({"port": port}), flush=True)

    server = uvicorn.Server(config)
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
