# Theories Backend (PoC)

FastAPI backend for the Research Assistant Tauri app. It hydrates
[is.theorizeit.org](https://is.theorizeit.org) and stores each theory's
`<div id="bodyContent">` as a local HTML file. Document ingestion, linking,
retrieval, and the graph are added in later increments.

## Layout

    src-backend/
    +-- pyproject.toml
    +-- data/                      # runtime data (git-ignored)
    |   +-- theories/              # scraped theory HTML
    |   +-- logs/app.log           # JSON log file (redacted)
    +-- scripts/                   # dev server + smoke check
    +-- app/
    |   +-- main.py  config.py  deps.py  security.py  cli.py
    |   +-- api/                   # health, config, jobs, wiki, files, search, graph, links, eval
    |   +-- core/                  # settings, logging, errors, ids
    |   +-- gateway/               # LLM, embeddings, rerank, cache, capabilities
    |   +-- stores/                # sqlite, vector, graph + interfaces.py
    |   +-- pipelines/             # wiki, docs, extraction, resolution, linking, retrieval
    |   +-- jobs/                  # queue, runner, stages
    |   +-- schemas/               # shared Pydantic models
    +-- tests/
        +-- unit/  integration/  fixtures/

Only the wiki/theories flow is implemented so far.

## Running

Everything runs in the existing `poc-backend` conda environment:

    conda run -n poc-backend python -m app --port 0 --token dev-token --data-dir ./data

`--port 0` picks a free port; the CLI prints one JSON line `{"port": N}` once
ready. For a fixed port during development use `scripts/dev.sh` (port 8766).
The token can also come from `APP_AUTH_TOKEN`.

## API

All routes require `Authorization: Bearer <token>`; the health route is also
protected.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health`, `/api/health` | Status + file count |
| POST | `/v1/theories/hydrate` | Start a background scrape (202, returns `job_id`) |
| GET | `/v1/theories/jobs/{job_id}` | Job status: `stage`, `progress`, `detail`, `result` |
| GET | `/v1/theories` | All theories (latest file each) with title, url, file, tokens |
| GET | `/v1/theories/{slug}` | One theory incl. the stored `bodyContent` HTML fragment |

Errors use the uniform shape `{code, message, details}`. Logs are JSON lines in
`<data-dir>/logs/app.log` with API-key-style values redacted.

## Tests and tooling

    conda run -n poc-backend python -m pytest
    conda run -n poc-backend ruff check app tests
    conda run -n poc-backend mypy app

Versions are pinned in `pyproject.toml`; the dev extras (`pytest`,
`pytest-asyncio`, `ruff`, `mypy`) are installed in `poc-backend`.

## Data

Scraped theories land in `data/theories/`, git-ignored because they can be
regenerated. One file per theory is named `<slug>_<run timestamp>.html`, and
`theories_index.json` records per-run metadata (last 20 runs). Sample wiki
HTML and a sample PDF live in `tests/fixtures/`.

## Sidecar notes

When bundled, Tauri spawns this app itself: it passes a random `--token` and a
data dir under the Tauri app data directory, reads the `{"port": N}` line from
stdout, and kills the child on exit. Production sidecar packaging (PyInstaller)
is planned for increment 13; until then set `POC_BACKEND_BINARY` when running
in `POC_BACKEND_MODE=prod`.
