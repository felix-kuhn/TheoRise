# Changelog

## 2026-10-29 - Increment 01: Scaffold

- Backend: `create_app()` factory, `python -m app` CLI with `--port 0` port
  discovery (prints `{"port": N}`), bearer-token auth on every route,
  Tauri/Vite-only CORS, JSON file logging with secret redaction, and uniform
  `{code, message, details}` error responses.
- Backend: `/health` and `/api/health` return status, version, data dir, and
  theory count.
- Tauri: `start_backend` spawns the backend with a random token (dev uses the
  `poc-backend` interpreter; prod uses `POC_BACKEND_BINARY`), exposes
  `get_backend_info()`, and kills the child on exit. HTTP scope restricted to
  `http://127.0.0.1:*` via the Tauri HTTP plugin.
- Tauri: aligned `@tauri-apps/api` (2.12.4) and `@tauri-apps/plugin-http`
  (2.8.3) with the Rust crates so `tauri dev` starts without version warnings.
- Frontend: authenticated `api/client.js` (fetch + SSE + typed errors),
  TanStack Query health polling, `BackendStatus` badge, and sidebar shell with
  Library, Search, Graph, Links, Settings, Chat, History, and Theories views.
- Tooling: pinned backend deps plus ruff, mypy, pytest-asyncio; ESLint,
  Prettier, Vitest + Testing Library; `scripts/ci.sh` runs everything.
- Tests: backend health/auth/error/CLI-startup coverage (18 passed) and
  frontend client-token + badge ok/error coverage (5 passed).
