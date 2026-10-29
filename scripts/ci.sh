#!/usr/bin/env bash
# CI for increment 01. All backend commands run inside the existing
# poc-backend conda environment (see docs/plan/00_OVERVIEW.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/src-backend"

cd "$BACKEND"

echo "==> Backend: pytest"
conda run -n poc-backend --no-capture-output python -m pytest -q

echo "==> Backend: ruff"
conda run -n poc-backend --no-capture-output ruff check app tests

echo "==> Backend: mypy"
conda run -n poc-backend --no-capture-output mypy app

cd "$ROOT"

echo "==> Frontend: eslint"
bun run lint

echo "==> Frontend: vitest"
bun run test

echo "==> Frontend: build"
bun run build

echo "==> Frontend: prettier"
bun run format:check

echo "CI passed."
