# P0.1 Live Test Report (OpenD / real environment)

## Status: NOT EXECUTED (environment unavailable)

- Date: 2026-11-11
- Target: `127.0.0.1:11111` (default OpenD)
- Check: `uv run mooc doctor` → `[ERROR] OpenD not reachable at 127.0.0.1:11111: [Errno 111] Connection refused`

## Tests not run
| Area | Tests/commands | Reason |
|---|---|---|
| SDK/OpenD connectivity & live quote/trade paths | `tests/test_opend_live.py`, `tests/test_option_live.py`, `tests/test_trade_live.py`, live-marked cases | Require running OpenD, login, and market/trade permissions |
| Daemon + IPC against live OpenD | Manual `mooc daemon run` + `mooc probe ...` / TUI with real data | OpenD unreachable |
| Real quote source/provenance verification | Live snapshot/volatility/events/analysis flows | Cannot observe OpenD realtime/delayed status without connection |

## Required to complete live verification
1. Start OpenD and ensure quote/trade login as needed (SIMULATE context for trade reads).
2. Re-run `uv run mooc doctor`.
3. Run `uv run python -m pytest -q -m live` (or targeted live tests) and record pass/fail/skip with environment details.
4. Validate daemon lifecycle with live backend: start/stop, IPC requests (`snapshot`, `volatility`, `events`, `analyze`, trade reads), reconnect behavior, and confirm no real-trade side effects.

## SIMULATE note
Code/policy inspection and non-live tests indicate SIMULATE-only trade env enforcement and read-only trade probes; live confirmation still pending OpenD-backed run.
