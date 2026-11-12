# Known Issues (updated after P0.2)

Issues tracked from baseline inspection and P0.2 implementation. **P0.2-addressed** items are resolved in non-live scope unless noted; remaining items are open for P0.3/P0.4 or later.

## P0.2 addressed (implemented)
1. **Unified analysis context/entry (resolved):** `services.analysis.run_analysis` is the single business entry for daemon `GetAnalysis` and CLI `probe analyze`, with `AnalysisContext` carrying `analysis_id` (generated at entry), `requested_at`, `rules_version`, and explicit account fields.
2. **CLI vs daemon account/risk divergence (resolved):** IPC `GetAnalysis` accepts optional `acc_id/trd_env/currency`; daemon resolves account via policy-checked funds lookup and passes consistent context to unified analysis. CLI no longer maintains a separate core compute/record path.
3. **Account semantics (resolved):** `account_equity` (total_assets), `available_cash` (cash), and `buying_power` (power) kept distinct; missing/unavailable values never fabricated and never used to produce fake position sizing. Sizing uses explicit positive equity only.
4. **Rules version traceability (resolved):** deterministic SHA-256 over normalized effective loaded rules (`compute_rules_version`); load failure -> `rules_version=None` and `RULE_NOT_CONFIGURED` (no invented version).
5. **Analysis vs persistence status separation (resolved):** responses include `analysis_status` and `persistence` (`saved|skipped|failed|not_attempted`); persistence failures are explicit and do not discard computed analysis results.
6. **IPC backward compatibility (resolved in tested cases):** old `GetAnalysis(code)` requests accepted; `AnalysisResult` retains `output` and adds optional traceability/status fields. New optional account fields default safely.

## Data quality & snapshot provenance (P0.3 target, open)
7. **Source/status fidelity limited.** `opend/quote.stock_snapshot` and `opend/option.snapshots` largely infer REALTIME/staleness from `update_time`; OpenD delayed/historical/simulated/unknown states not distinctly preserved.
8. **No unified quote validation.** Missing/negative/bid>ask/one-sided quotes, stock-vs-option time skew, and multi-leg quote consistency checks not centralized.
9. **Input snapshots not durably linked to decisions.** Analysis does not persist/reference exact snapshot/chain ids used (P0.3 scope).
10. **Freshness not fully context-differentiated.** Multi-leg consistency windows and per-instrument policies not enforced.

## Persistence semantics (partially addressed)
11. **Traceability in DB:** `analysis_id`/`rules_version`/context carried in decision payload/output, but no dedicated DB columns/indexes or snapshot linkage tables (deferred; no P0.2 migration).
12. **Recording idempotency key:** still `(symbol, strategy, created_at)`; `analysis_id` is unique per request but not the DB uniqueness key.
13. **Migration strategy basic:** DDL apply + `user_version` stamp without incremental migrations; future additive changes must be handled carefully.

## Pricing & calculation audit (P0.4 target, open)
14. **`float` used for money/prices broadly.** Precision/rounding policy and audit pending.
15. **Edge cases/systematic audit pending.** Multipliers, non-standard contracts, missing/one-sided/zero/negative quotes, bid>ask, expiry/DTE boundaries, and uncomputable-result handling need verification.
16. **Executable price source consistency.** Per-leg bid/ask vs authoritative combo pricing paths require audit.

## Environment / validation
17. **OpenD unavailable in current env.** `mooc doctor` connection refused (`127.0.0.1:11111`); live quote-source/provenance and daemon+OpenD end-to-end verification not performed.
18. **Non-live baseline/after P0.2 green:** `191 passed, 4 deselected`, ruff/mypy/format clean.

## Notes
- Daemon caches loaded rules and `rules_version` at service initialization; rule file changes require restart/reload semantics consistent with prior behavior.
- `analysis_status` classification is minimal/conservative for P0.2 and should be refined with P0.3 data-quality signals.
