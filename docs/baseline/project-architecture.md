# P0.1 Project Architecture (Baseline)

## 1. Runtime topology
- **Pattern:** Daemon-mediated: `OpenD <- moomoo-api (SDK) -> daemon <- typed IPC (Unix socket) -> CLI/TUI`.
- **Daemon (`mooc daemon run|status|stop|serve`)**: owns SDK connections (`OpendClient`), accepts Unix-socket clients, decodes typed requests, dispatches to services, returns typed responses. Socket/PID/lock/log managed under runtime dir (default `~/.mooc`, `MOOC_RUNTIME_DIR` override).
- **CLI (`mooc ...`)**: loads config, for `probe` commands typically connects directly to OpenD via `OpendClient` for read-only operations; for daemon-managed flows can use IPC client; `doctor` checks TCP/SDK state.
- **TUI (`mooc tui`)**: Textual app, talks to daemon via `IpcClient` (blocking calls run in workers); projection/interaction only.

## 2. Major modules and responsibilities

### Entry/config/policy
- `src/mooc/cli.py`: argparse CLI, command handlers (`doctor`, `probe *`, `daemon *`, `tui`), direct-SDK probe paths, background daemon spawn, formatting.
- `src/mooc/config.py`: dataclasses + TOML/env loading (`mooc.toml`, `MOOC_*`), validation/fail-fast (`OpendConfig`, `TradingConfig`, `UiConfig`, `StorageConfig`, `DataQualityConfig`, `RulesConfig`, `RiskConfig`).
- `src/mooc/policy.py`: resolves/validates trade environment (SIMULATE-only by default config).

### Daemon & IPC
- `src/mooc/daemon/lifecycle.py`: runtime paths, startup lock, liveness checks.
- `src/mooc/daemon/server.py`: asyncio Unix server; routes requests to `OptionDataService`, `TradeService`, or `MarketDataService` based on protocol request groups; SDK/service calls executed via `asyncio.to_thread`; frame-size bounded.
- `src/mooc/ipc/protocol.py`: Pydantic request/response models (discriminated by `kind`), DTOs, encode/decode, `MAX_FRAME_BYTES`, request group tuples (`TRADE_REQUESTS`, `MARKET_REQUESTS`).
- `src/mooc/ipc/client.py`: synchronous request/response over Unix socket with timeout and error wrapping.

### OpenD/SDK access (`src/mooc/opend/`)
- `client.py`: manages quote context and lazy trade context, TCP check, `health`, lifecycle/close.
- `quote.py`: stock snapshots/last/bid-ask with freshness (`parse_update_time` US/Eastern→UTC).
- `option.py`: expirations, chain, per-leg quotes, option snapshots, combo analysis.
- `market.py`: historical klines/bars.
- `volatility.py`: underlying historical IV/HV.
- `events.py`: earnings/economic calendars.
- `trade.py`: accounts/funds/positions/orders (read-only).
- `watchlist.py`: groups/members/ATM summaries.
- `values.py`, `errors.py`: value parsing/OK checks and error types (`MoocError`, connectivity/rejection errors).

### Domain (`src/mooc/domain/`)
- `market.py`: `DataSource`, `QuoteQuality`, staleness helpers, `StockQuote`, `OptionSnapshot`, `Bar`, `VolatilityPoint`.
- `options.py`, `watchlist.py`, `trade.py`: option/leg/contract/watchlist/trade domain types.
- `events.py`: event types/models.
- `strategy.py`, `rules.py`: strategy/pricing and rule model types (tri-state/unset semantics).
- `risk.py`: Greeks, position/risk/exit signal types and drawdown actions.
- `decision.py`: `TradeStatus` state machine helpers and `DecisionOutput` (14.1-style fields, `to_dict`).
- `journal.py`: journal/confirmation models.

### Services (`src/mooc/services/`)
- `option_data.py`: handles option-chain/expirations/combo and watchlist/underlying summary IPC requests.
- `trade.py`: handles read-only trade IPC requests with policy-resolved env/currency and DTO mapping.
- `market_data.py`: handles snapshot/volatility/events/analysis/journal IPC; serializes SDK access with lock; loads rules; best-effort decision recording.
- `analyze.py`: orchestrates data fetch (bars, vol history, snapshot, events), scanner + selector + pricing + risk to build `DecisionOutput`.
- `scanner.py`, `selector.py`, `volatility.py`, `pricing.py`, `risk.py`, `decision.py` (service), `rules.py`: core analysis/pricing/risk/rule-loading logic (largely pure/domain-oriented except fetch orchestration in analyze path).
- `recording.py`: persists decision to candidate/signal/risk_snapshot (atomic best-effort per call semantics).
- `journal.py`: computes forward performance from journal entries.
- `monitor.py`: monitored leg/cost-to-close/exit-signal helpers (used by CLI monitor flow).

### Storage (`src/mooc/storage/`)
- `schema.py`: SQLite DDL (schema v2) and `SCHEMA_VERSION`.
- `db.py`: connect/open/migrate helpers (WAL, foreign keys, busy timeout).
- `repo.py`: upsert/query/write helpers for quotes/contracts/events/candidates/signals/risk snapshots/journal/confirmations and decision-record existence check.

### UI
- `src/mooc/tui/app.py`: Textual tabs (Watchlist, Chain, Strategy, Account, Orders, Analysis, Journal), IPC-driven loads, worker threading, request generation/stale-response guards.

## 3. Key data/control flows

### A. Daemon IPC flow
`Client (CLI/TUI) -> IpcClient.request -> Unix socket -> DaemonServer._handle_client -> decode_request -> route by request type -> service.dispatch (to_thread) -> encode_response`.

### B. Analysis (daemon path)
`GetAnalysis(code)` -> `MarketDataService._analysis` -> `analyze_symbol(client, code, rules, config)` -> fetch bars/vol history/stock snapshot/events (+ optional chain/snapshots for selection) -> scan/decide/price/risk -> `DecisionOutput` -> `_record` best-effort to SQLite -> `AnalysisResult(output dict)`.
- Current gap: no `analysis_id`, no account context in IPC, no snapshot linkage, persistence failure not surfaced in response.

### C. Analysis (CLI probe path)
`mooc probe analyze <code> [--acc-id]` -> direct OpenD + local `analyze_symbol` (optionally fetch funds for equity) -> best-effort local DB record -> print JSON/text with recorded/note. Can diverge from daemon behavior.

### D. Trade read flow
IPC/CLI -> `resolve_trd_env` (policy) -> `opend.trade` queries -> DTO/domain mapping -> response/output. Write/order submission not implemented.

### E. Monitor (CLI)
`probe monitor` -> list positions + option snapshots + rule thresholds -> per-position (currently single-leg approximation) cost/signals with stale suppression -> output. No unified daemon/IPC monitor service.

## 4. Persistence model (baseline)
- SQLite, WAL, schema v2 (`symbols`, `stock_quotes`, `option_contracts`, `option_quotes`, `events`, `trade_candidates`, `trade_signals`, `risk_snapshots`, `trade_journal`, `confirmations`).
- Market tables carry provenance/freshness fields (`observed_at`, `source`, `is_stale`, `missing_fields`/timestamps) where defined.
- Migrations are DDL-apply + version stamp (no incremental migration framework).

## 5. Configuration & safety
- TOML (`mooc.toml`) + env overrides; rules path configurable; data-quality freshness thresholds configurable.
- Default trading policy SIMULATE-only; disallowed envs rejected before SDK trade calls.
- No automated real-order submission path present.
