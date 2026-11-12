# P0.2 Design & Implementation: Unified Analysis Context

## 1. Baseline (before P0.2)
- **IPC:** `GetAnalysis` only `{code}`; daemon `MarketDataService._analysis` called `analyze_symbol` without account context and best-effort recorded without surfacing persistence outcome.
- **CLI:** `probe analyze` loaded rules, optionally fetched funds by `--acc-id`, passed `account_equity` to `analyze_symbol`, and performed separate local best-effort recording — diverging from daemon semantics.
- **Traceability:** no `analysis_id`, no `rules_version`, no explicit analysis/persistence status split, no structured account context (equity/cash/buying power conflation risk).

## 2. Implemented design (minimal, compatible)

### 2.1 Models (`src/mooc/domain/analysis.py`, `src/mooc/domain/decision.py`)
- `AccountContext`: `account_id`, `trd_env`, `currency`, `account_equity`, `available_cash`, `buying_power` (all nullable/explicit; `total_assets` mapped to equity, `cash` to available cash, `power` to buying power; never cross-filled/fabricated).
- `AnalysisContext`: `analysis_id` (UUID), `symbol`, `requested_at` (tz-aware UTC), `rules_version`, optional `account`, snapshot refs placeholders, `entrypoint`.
- `AnalysisResultStatus`: `OK | INSUFFICIENT_DATA | RULE_NOT_CONFIGURED | INVALID_INPUT | CALCULATION_ERROR | STALE_DATA | PERSISTENCE_ERROR`.
- `PersistenceStatus`: `saved | skipped | failed | not_attempted` (+ message), separate from analysis outcome.
- `DecisionOutput` extended additively with `analysis_id`, `requested_at`, `rules_version`, `analysis_status`, `account`, `context` (all existing `to_dict()` keys preserved).

### 2.2 Rules version (`src/mooc/services/rules.py`)
- `compute_rules_version(rules, rules_path)`: deterministic SHA-256 over canonical JSON of normalized effective loaded rules (path + rule fields including UNSET/null tri-state). Reflects actual loaded content; load failure => `rules_version=None` and explicit error/status (no fabricated version).

### 2.3 Unified business entry (`src/mooc/services/analysis.py`)
- `load_rules_with_version`, `resolve_account_context` (policy-checked funds lookup), `build_analysis_context`, `run_analysis`, `persist_analysis`, `analysis_result_to_ipc`.
- `run_analysis(...)` is the single entry for CLI and daemon: generates `analysis_id` at entry, computes with explicit equity only when available, derives `analysis_status`, attaches traceability, persists with explicit `PersistenceStatus`, returns `AnalysisRunResult` (analysis output preserved even on persistence failure).
- Account requested but unavailable -> explicit note and `INSUFFICIENT_DATA` (no fake sizing). Rules unavailable -> `RULE_NOT_CONFIGURED`.

### 2.4 Integration
- **Daemon (`services/market_data.py`):** resolves optional account context from IPC request, uses cached rules+version/load error, runs unified analysis, returns enriched `AnalysisResult`.
- **CLI (`cli.py`):** `probe analyze` uses same service (load/resolve/run/persist), accepts `--acc-id/--trd-env/--currency`, reports separated statuses and compatibility `recorded/record_note`.
- **IPC (`ipc/protocol.py`):** `GetAnalysis` adds optional `acc_id`, `trd_env`, `currency`; `AnalysisResult` keeps `output` and adds optional `analysis_id`, `symbol`, `requested_at`, `rules_version`, `analysis_status`, `persistence`, `account`, `notes`.

### 2.5 Persistence and traceability
- No schema migration. Traceability/context/status embedded in decision output/payload and response. Persistence success/failure/skipped is explicit and distinct from analysis success.
- Recording idempotency semantics unchanged at DB key level; `analysis_id` is unique per request and included in payload/response.

## 3. Compatibility
- Old `GetAnalysis(code)` requests valid. New response fields additive; `output` remains primary for existing consumers (TUI continues to read `output`). CLI JSON/text extended additively.

## 4. Verification
- New tests: `tests/test_p0_2_analysis_context.py` (context/IDs/versioning, account semantics, missing-account no sizing, unified-entry CLI-vs-daemon core consistency with unique IDs, persistence separation, IPC compat, rules-load error).
- Full non-live suite, ruff, format, mypy passing at implementation time (see `docs/p0/test-report.md`, `docs/p0/p0.2-implementation-report.md`).

## 5. Deferred to P0.3/P0.4
- Quote snapshot persistence/linkage and unified data-quality/consistency validation.
- Pricing formula/edge/multiplier/precision audit and richer status classification for stale/invalid inputs.
