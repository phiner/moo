# P0.1 Validation Report

## Environment / commands executed
- Date: 2026-11-11
- Workspace: `/home/phiner/projects/mooc` (branch `main`, clean at baseline)
- Project env: used `uv run ...` for project-managed tooling/deps

| Command | Result | Notes |
|---|---|---|
| `uv run python -m pytest -q -m "not live"` | PASS | `182 passed, 4 deselected in 8.70s` (live tests deselected) |
| `uv run ruff check .` | PASS | `All checks passed!` |
| `uv run ruff format --check .` | PASS | `92 files already formatted` |
| `uv run mypy` | PASS | `Success: no issues found in 53 source files` (note in `opend/client.py:106`: untyped-def body check note) |
| `uv run mooc doctor` | FAIL (environment) | `[ERROR] OpenD not reachable at 127.0.0.1:11111: [Errno 111] Connection refused` — OpenD not running |
| `scripts/validate.sh` | Equivalent checks passed | Script runs ruff check/format, mypy, pytest non-live; each command above passed individually in this env |

## Daemon / IPC verification (non-live, via existing tests)
Baseline non-live suite includes and passed: `tests/test_daemon_lifecycle.py`, `tests/test_daemon_background.py`, `tests/test_ipc_protocol.py`, `tests/test_ipc_client.py`, `tests/test_market_service.py`, `tests/test_trade_service.py`, `tests/test_watchlist_service.py`. These cover server roundtrip/error handling and cleanup, startup lock behavior, protocol encode/decode/validation, client timeout behavior, and service dispatch/error mapping without requiring OpenD.

## SIMULATE safety boundary (baseline evidence)
- Config defaults/policy enforce SIMULATE-only trading env (`config.TradingConfig`, `policy.resolve_trd_env`); disallowed envs (e.g. REAL) rejected in trade service (`tests/test_trade_service.py::test_disallowed_env_is_rejected`).
- Implemented trade operations are read-only queries (accounts/funds/positions/orders) in `opend/trade.py`, `services/trade.py`, CLI probe trade commands; no order submission path found in current codebase.
- `mooc doctor` only checks connectivity/login/market state; no trading side effects by design.

## Skipped / not executed
- `pytest -m live` / `tests/test_*_live.py`: not executed (require running OpenD and permissions). 4 tests deselected.
- Live daemon+OpenD end-to-end (real snapshots/chain/analysis/account data): not executed (OpenD unreachable).
- TUI manual interactive verification against live daemon: not executed.

## Blocking issues at baseline
- No code/test/tooling blockers in non-live validation. External dependency unavailable: OpenD at `127.0.0.1:11111`.
- Direct `python3 -m pytest` outside project env failed collection (`ModuleNotFoundError: mooc`), so validation must run in project environment (`uv run`).
