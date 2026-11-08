#!/usr/bin/env bash
# Canonical local validation for mooc. Run from anywhere in the repo.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ruff check =="
uv run ruff check .
echo "== ruff format --check =="
uv run ruff format --check .
echo "== mypy =="
uv run mypy
echo "== pytest (non-live) =="
uv run python -m pytest -q -m "not live"
echo "ALL CHECKS PASSED"
