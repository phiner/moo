# P0.4 Pricing & Strategy Calculation Audit Report (Baseline / Plan)

## 1. Status
- **Audit execution:** NOT STARTED (no code changes or new independent pricing tests added in this iteration).
- **Baseline evidence:** existing pricing/risk/analyze tests pass in non-live suite (`182 passed` total). This report inventories scope, current implementation points, risks, and the required audit/test plan.

## 2. Current implementation inventory

### Pricing (`src/mooc/services/pricing.py`)
- Implements: bull/bear put/call vertical spreads (credit/debit), cash secured put, covered call, conversion (and helpers as present).
- Uses `CostModel` (per-contract fee, slippage per share) in spread pricing paths; multiplier parameter present in key functions (defaults observed as standard 100 in code paths—must be verified exhaustively).
- Returns `PricingResult` with `net_premium`, `max_profit`, `max_loss`, `breakeven`, `cash_required` etc. (domain `strategy.PricingResult`).

### Selection & executable inputs (`src/mooc/services/selector.py`, `services/analyze.py`)
- `select_spread` chooses contracts using `ContractQuote` with bid/ask/delta; computes `net_per_share` as sell-short bid minus buy-long ask (credit) or inverse (debit) from leg snapshots.
- `analyze._priced` builds pricing from selected short bid / long ask (defaults missing to 0.0 in code—**audit risk**: must not price on fabricated zeros/invalid quotes).
- Combo authoritative pricing exists in `opend/option.combo_analysis` / `services/option_data` for explicit combo requests, but analyzed strategy pricing path is per-leg based.

### Risk sizing (`src/mooc/services/risk.py`)
- `assess_trade` requires positive finite `max_loss_per_contract`, valid `account_equity`, and `max_account_risk_pct`; otherwise returns `passed=False` with reasons. Uses `math.floor` for contracts.

### Monitor (`src/mooc/services/monitor.py`, CLI monitor)
- `cost_to_close` per-share: buy back short at ask (`action SELL` close), sell long at bid; returns `None` if required quote missing. Credit-style signal applicability handled in CLI logic (single-leg approximation).

### Existing tests (`tests/test_pricing.py`, `tests/test_risk.py`, `tests/test_analyze.py`, `tests/test_selector.py`, etc.)
- Cover representative spread/CSP/covered call/debit/conversion cases, cost impact, basic invalid strikes, risk sizing pass/fail, and selection/analyze integration scenarios. **Not sufficient** for full P0.4 audit (independent benchmarks, full edge matrix, multiplier non-100, all boundary/invalid-quote behaviors, precision policy).

## 3. Audit checklist (required)

### A. Basic option data & units
- [ ] Call/Put identification and strategy direction mapping.
- [ ] Strike/expiry/DTE calculations (including expiry-day and <1 day cases).
- [ ] ATM/ITM/OTM handling where relevant.
- [ ] Contract multiplier correctness for all strategies (standard and non-standard); no hidden assumption of 100.

### B. Quote direction (executable vs reference)
- [ ] Buy legs priced at Ask, sell legs at Bid for cost/revenue estimation.
- [ ] Mid used only as reference, never as guaranteed executable price.
- [ ] Multi-leg net credit/debit derived from correct leg sides.

### C. Strategy formulas (independent hand-calculated expected values)
- [ ] Bull Put Credit Spread: net credit, max profit, max loss, breakeven.
- [ ] Bear Call Credit Spread: net credit, max profit, max loss, breakeven.
- [ ] Bull Call Debit Spread: net debit, max loss, max profit, breakeven.
- [ ] Bear Put Debit Spread: net debit, max loss, max profit, breakeven.
- [ ] Cash Secured Put / Covered Call: premium, cash/stock considerations, breakeven, max loss/profit semantics and assumptions (esp. with/without stock cost basis).
- [ ] Conversion (if in-scope for current calculations): incremental P&L with executable prices and costs; clearly labeled assumptions.

### D. Costs, fees, slippage, and precision
- [ ] Fee/slippage model applied consistently and configurably; no double-counting.
- [ ] Rounding/precision policy defined and tested (current float-based; assess `Decimal` adoption feasibility or guarded numeric handling without broad breakage).

### E. Edge and invalid cases (must not yield fake-valid results)
- [ ] Missing/one-sided/zero/negative quotes, bid>ask, extreme spreads.
- [ ] Uncomputable inputs -> explicit non-computable/invalid state (not coerced to misleading numbers).
- [ ] Deep ITM/OTM, negative/impossible net economics.
- [ ] Expiry boundaries, DTE anomalies.

## 4. Findings / suspected issues to verify
1. **Potential fabricated pricing inputs:** `analyze._priced` uses `selection.short.bid or 0.0` / `selection.long.ask or 0.0`; selector currently filters for non-None bid/ask/delta, but end-to-end path must guarantee no zero-substitution for missing executable prices.
2. **Multiplier propagation:** ensure chain/contract multipliers flow into pricing/risk (per-contract $) consistently; tests should include non-100 multiplier cases where supported.
3. **Credit spread max-loss floor/edge cases:** verify formula correctness when premiums imply edge conditions; ensure bounded and sensible.
4. **Per-share vs per-contract units:** confirm consistency across pricing, risk sizing, monitoring (`cost_to_close` per-share), and reporting.
5. **Float precision:** accumulation/comparison/rounding may affect thresholds (e.g. risk budgets, take-profit/stop multiples); define acceptable tolerance or migrate critical paths carefully.

## 5. Planned test additions (P0.4)
- Independent, hand-calculated parameterized tests per strategy: normal, profit/loss/breakeven, boundary, abnormal quotes.
- Quote-direction tests (buy ask / sell bid) and multi-leg netting.
- Multiplier (100 and non-standard) tests.
- Invalid/uncomputable input tests asserting explicit failure/invalid status (no numeric result presented as valid).
- Decimal/precision and rounding tests aligned with chosen policy.
- Regression run of existing pricing/risk/analyze/selector/monitor suites.

## 6. Exit criteria (when implemented)
- [ ] Formula checklist completed with evidence.
- [ ] Independent tests for all in-scope strategies.
- [ ] Quote direction and multipliers verified.
- [ ] Max profit/loss/breakeven verified.
- [ ] Invalid quotes/boundaries cannot produce valid trade suggestions.
- [ ] Precision/rounding behavior defined and tested.
- [ ] All existing and new tests pass.
