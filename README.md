# TheoRise

Offline-capable desktop research app: a Tauri shell (Rust) with a React
frontend and a local FastAPI backend. Currently, the backend hydrates and stores theory
pages from [is.theorizeit.org](https://is.theorizeit.org); document ingestion,
linking, retrieval, and the knowledge graph are added in later increments.

## Layout

    src-tauri/        Tauri shell (Rust): spawns/kills the backend, HTTP scope
    src/              React + Vite frontend
    src-backend/      FastAPI backend (Python, runs in the `poc-backend` conda env)
    docs/plan/        Increment plans and conventions (start with 00_OVERVIEW.md)
    scripts/ci.sh     One-shot CI: backend + frontend checks

## Prerequisites

- The existing `poc-backend` conda environment (Python 3.12). The backend is
  never run with system Python.
- `bun` for the frontend and `cargo` for the Tauri shell.

## Development

Backend alone (from `src-backend/`):

    conda run -n poc-backend python -m app --port 0 --token dev-token --data-dir ./data

The CLI prints one JSON line `{"port": N}` once the server is ready, then
serves on `127.0.0.1`. Every route requires `Authorization: Bearer <token>`.

Frontend in a browser (Vite):

    VITE_BACKEND_URL=http://127.0.0.1:8766 VITE_BACKEND_TOKEN=dev-token bun run dev

Desktop app (Tauri dev spawns the backend itself):

    bun run tauri dev

Tauri resolves the backend interpreter from `POC_BACKEND_PYTHON` (default: the
interpreter of the `poc-backend` env, looked up via `conda`). The shell starts
the backend with a random token, reads the reported port, and exposes
`get_backend_info()` to the frontend. HTTP calls are scoped to `127.0.0.1`.

## Checks

    bash scripts/ci.sh

The script runs, inside `poc-backend` only: pytest, ruff, mypy. It then runs
eslint, Prettier, Vitest, and the Vite build.

## Status

Increment 01 is complete: authenticated backend with health endpoint, JSON
logging, uniform errors, CLI port discovery, Tauri process management, and the
React app shell with backend status badge. See `docs/CHANGELOG.md`.
