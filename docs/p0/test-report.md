# P0 Test Report (updated after P0.2)

## Scope
- **P0.1:** baseline inspection and validation documentation.
- **P0.2:** unified analysis context/entry, account semantics, `analysis_id`/`rules_version`, separated analysis vs persistence status, backward-compatible IPC/CLI changes, and P0.2 tests. **P0.3/P0.4 not implemented.**

## Executed

| Command | Passed | Failed | Skipped/Deselected | Notes |
|---|---:|---:|---:|---|
| `uv run python -m pytest -q tests/test_p0_2_analysis_context.py` | 9 | 0 | 0 | New P0.2 coverage: context, unique IDs, deterministic rules version, missing-account no fabricated sizing, equity/cash semantics, CLI-vs-daemon core-result consistency with unique IDs, persistence-failure separation, IPC compat, rules-load error status |
| `uv run python -m pytest -q tests/test_ipc_protocol.py tests/test_analyze.py tests/test_market_service.py tests/test_cli_trade.py` | 46 | 0 | 0 | Targeted regression for protocol/analyze/market/CLI trade |
| `uv run python -m pytest -q -m "not live"` | 191 | 0 | 4 deselected | Full non-live suite (includes P0.2 tests) |
| `uv run ruff check .` | n/a | 0 | n/a | Pass |
| `uv run ruff format --check .` | n/a | 0 | n/a | Pass |
| `uv run mypy` | n/a | 0 | n/a | Pass; note `src/mooc/opend/client.py:106` (untyped-def body) |
| `uv run mooc doctor` | n/a | 1 | n/a | Environment: `[ERROR] OpenD not reachable at 127.0.0.1:11111: [Errno 111] Connection refused` |

## Not executed (with reasons)

| Command / suite | Reason |
|---|---|
| `scripts/validate.sh` (single invocation) | Equivalent component checks executed and passed (`ruff`, `ruff format --check`, `mypy`, `pytest -q -m "not live"`) |
| `uv run python -m pytest -q -m live` (4 tests) | Requires running OpenD and market/trade permissions; unavailable |
| Daemon + IPC integration against live OpenD | OpenD unreachable |
| P0.3 snapshot/quote-quality/consistency/persistence-linkage tests | P0.3 not implemented |
| P0.4 pricing audit independent formula/edge/precision tests | P0.4 not implemented |
| Manual TUI interactive verification against live daemon | OpenD/daemon-live environment unavailable |

## Defects found / fixed in P0.2
- **Fixed (P0.2 scope):** CLI vs daemon analysis context divergence for account/risk inputs via unified `services.analysis.run_analysis`; added `analysis_id`/`rules_version` traceability, explicit account field separation, and separated analysis vs persistence status reporting.
- **No new non-live regressions observed.** Baseline/P0.3/P0.4 gaps remain as documented.

## Exit criteria status
- **P0.2 targeted criteria:** met in non-live scope (unified entry/context, traceability fields, account semantics, status separation, IPC compatibility, new tests, regressions/quality gates green).
- **P0 overall Definition of Done:** **NOT MET** (P0.3, P0.4 incomplete; live verification pending).
