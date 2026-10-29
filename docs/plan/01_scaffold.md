# 01 - Scaffold: Tauri + React + FastAPI sidecar

## Objective
A running desktop shell whose React UI calls an authenticated FastAPI backend and shows backend health.

## Tasks
1. Create repo layout from `00_OVERVIEW.md`.
2. **Backend**
   - `pyproject.toml` with deps; `app/main.py` creates FastAPI app with `create_app()` factory.
   - CLI entry: `python -m app --port 0 --token <T> --data-dir <path>`; port 0 = pick free port, print one JSON line `{"port": N}` to stdout once ready.
   - `security.py`: dependency requiring header `Authorization: Bearer <token>` on all routes except none (health also protected). CORS: allow only the Tauri/Vite origins (`tauri://localhost`, `http://localhost:1420`, `http://tauri.localhost`).
   - `GET /api/health` -> `{status, version, data_dir}`.
   - Structured logging (JSON) to `<data-dir>/logs/app.log` with secret-redaction filter.
   - Uniform error handler (see global rule 9).
3. **Tauri**
   - Rust side: command `start_backend` spawns the Python process (dev: `python -m app`; prod: sidecar binary via `tauri.conf.json > externalBin`), generates a random token, reads the port line, exposes `get_backend_info()` -> `{baseUrl, token}` to the frontend; kills the child on exit.
   - Restrict the Tauri HTTP scope to `127.0.0.1`.
4. **Frontend**
   - `api/client.ts`: fetch wrapper using baseUrl + token, typed errors, SSE helper.
   - App shell with sidebar routes (Library, Search, Graph, Links, Settings) as placeholder pages; a status badge showing backend health via TanStack Query.
5. Tooling: ruff, mypy, pytest, eslint, prettier, Vitest; GitHub-Actions-style CI script `scripts/ci.sh` running everything.

## Tests
- pytest: health returns 200 with token, 401 without; port-0 startup prints JSON line (subprocess test).
- Vitest: client attaches the token; health badge renders ok/error states (mock fetch).

## Acceptance
- `npm run tauri dev` opens the window, badge shows "Backend OK".
- `scripts/ci.sh` passes.

## Checklist (increment 01)

- [x] Repo layout from `00_OVERVIEW.md` present and respected.
- [x] Backend: `create_app()` factory, pinned `pyproject.toml` deps, CLI with
  `--port 0` port JSON, bearer auth, CORS allow-list, `/api/health`, JSON
  logging with redaction, uniform errors.
- [x] Tauri: `start_backend` (dev interpreter + prod sidecar path),
  `get_backend_info()`, child killed on exit, HTTP scope restricted to
  `127.0.0.1`.
- [x] Frontend: authenticated API client, sidebar shell with placeholder
  routes, backend status badge via TanStack Query.
- [x] Tooling: ruff, mypy, pytest, eslint, prettier, Vitest, `scripts/ci.sh`.
- [x] Tests: backend health/auth/CLI (18 passed), frontend token + badge
  states (5 passed).
- [x] `scripts/ci.sh` passes; `npm run build`, `bun run lint`,
  `bun run test` green.
- [x] `docs/CHANGELOG.md` updated.

Production sidecar packaging (PyInstaller + `bundle.externalBin`) is deferred
to increment 13; the Rust launch path is already wired via
`POC_BACKEND_BINARY`.
