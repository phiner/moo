# 可行性分析：美股期权交易系统 V1.0

对应文档：[`trading-system-spec-v1.md`](./trading-system-spec-v1.md)
分析基准：现仓库 `mooc`（Python + moomoo OpenAPI + daemon/IPC/TUI 架构）+ 本机已安装的 `moomoo-api 10.12.7208`（接口名为实读源码核实，非猜测）。

---

## 0. 结论摘要

| 阶段 | 可行性 | 说明 |
|---|---|---|
| Phase 1 数据接入 + SQLite | **高** | 行情/期权链/Greeks/事件接口齐备；本仓库已实现大半，缺存储层 |
| Phase 2 定价与策略计算 | **高** | 纯数学，无数据依赖；多腿真实 Bid/Ask 可达 |
| Phase 3 筛选与决策引擎 | **高** | 趋势/波动率/事件/环境/合约筛选/NO TRADE 均可做；IV Rank/Percentile 数据其实可得（见 R2） |
| Phase 4 风险管理与持仓监控 | **高** | 风险公式明确；持仓 Greeks 可汇总 |
| Phase 5 Dashboard | **高** | 现有 Textual TUI 或 Streamlit 均可 |
| ~~Phase 6 回测与优化~~ | **不做** | 按决策取消：不做回测、不接入历史数据 |

**总体判断：V1.0 的"分析—建议—风控—看板"主体全部可行。**

> **重要更正（见第 2.2 / R1 / R2）：** 早前"moomoo 无历史期权数据、无 IV Rank"的判断有误。实测表明 **IV/HV 历史、IV Rank/Percentile、单合约历史 K 线、逐合约历史 IV/盘口/Greeks/量仓、期权成交量与持仓历史均可获取**。唯一缺口是"某历史时点全量合约的一次性链接口"（可用 `get_option_rank(trading_date=...)` + 单合约 K 线拼装）与长尾合约历史报价。按你的产品决策，本版本**仍不做回测**；**IV Rank/Percentile 已恢复纳入**。

**范围前提（已确认）：** 允许正股腿（Cash Secured Put / Covered Call / Conversion），但交易环境**仍仅限 SIMULATE**，不接实盘下单。

---

## 1. 现有代码库盘点（可直接复用）

| 能力 | 现状 | 位置 |
|---|---|---|
| 守护进程 + 类型化 IPC + TUI | 已有（daemon 为 SDK 唯一持有者） | `src/mooc/daemon`、`ipc`、`tui` |
| 期权到期/链/组合分析 | 已有 | `opend/option.py`、`services/option_data.py` |
| 自选股分组 + 多标的 ATM 摘要 | 已有（含限流） | `opend/watchlist.py` |
| 交易只读（账户/资金/持仓/订单） | 已有 | `opend/trade.py`、`services/trade.py` |
| 交易安全策略（SIMULATE-only） | 已有 | `policy.py`、`config.py` |
| 配置（TOML + 环境变量） | 已有 | `config.py` |
| 测试与校验（ruff/mypy/pytest） | 已有（94 项） | `tests/`、`scripts/validate.sh` |

→ 架构路线（Python + 模块化 + 配置驱动）与规格书第 13/14 章**一致**，可直接在此基础上扩展，无需推倒重来。

---

## 2. moomoo OpenAPI 能力矩阵（已核实）

### 2.1 已确认可用

| 需求 | 接口 | 备注 |
|---|---|---|
| 正股/期权快照（last/bid/ask/量） | `get_market_snapshot(code_list)` | 期权同样可查 |
| 期权到期日 / 期权链 | `get_option_expiration_date` / `get_option_chain(..., data_filter)` | 支持按 IV 等过滤 |
| 期权报价 + Greeks + IV | `get_option_quote(option_legs)` | 返回 `implied_volatility`、`delta/gamma/theta/vega/rho`、`open_interest`、`volume` |
| 历史 K 线（算 HV/趋势） | `request_history_kline` / `get_cur_kline` | **实测对期权代码同样可用**（可回放单合约历史价） |
| 期权标的 IV/HV 历史序列 | `get_option_underlying_his_volatility(code, begin_time, end_time)` | 每日 `iv`/`hv`/`underlying_price`，最长约 364 天、分页。**实测有数据** |
| 期权标的 IV Rank / Percentile | `get_option_underlying_rank(..., trading_date=...)` | 直接返回 `iv`、`iv_rank`、`iv_percentile`、`iv_change`、`hv`；可传历史交易日。**实测有数据** |
| 逐合约历史 IV/Bid-Ask/Greeks/量仓 | `get_option_rank(..., trading_date=...)` | 按历史交易日返回合约排行（200/页、可分页），含 `iv`、`bid_price`、`ask_price`、`delta/gamma/theta/vega/rho`、`open_interest`、`volume`。**实测有数据** |
| 期权标的历史成交量/持仓 | `get_option_underlying_his_statistic(...)` | 每日 option/call/put volume、OI、Put/Call 比。**实测有数据** |
| 期权市场历史成交量/持仓 | `get_option_market_statistic(option_market, data_type, ...)` | call/put 合计成交量、持仓量、PCR |
| 财报日历 | `get_earnings_calendar(market, begin_date, end_date, ...)` | **原生支持** |
| 经济事件日历（CPI/FOMC 等） | `get_economic_calendar(begin_date, end_date, market_list, importance)` | **原生支持** |
| 股息日历 / 股息数据 | `get_dividend_calendar`、快照股息字段、`get_dividend_rank` | 用于 Conversion/指派分析 |
| 财报前后价格表现 | `get_financials_earnings_price_move/history` | 事件策略辅助 |
| 市场状态 | `get_market_state(code_list)` | 分市场时段 |
| 账户/持仓/订单/成交/费用 | `OpenSecTradeContext`：`accinfo_query/position_list_query/order_list_query/deal_list_query/order_fee_query` | 费用可用于成本建模 |
| 自选股分组 | `get_user_security_group` / `get_user_security` | 标的输入来源 |
| 选股/排名 | `get_stock_filter`、`get_earnings_beat_rank`、`get_dividend_rank`、`get_option_event` | 可选 |

### 2.2 仍缺失 / 需外部数据

> **修正说明：** 早前"moomoo 无历史期权数据 / 无 IV Rank"的判断**有误**。实测下列数据均可获取：IV/HV 历史序列、IV Rank/Percentile（含历史交易日）、单合约历史 K 线、期权成交量/持仓历史。真正缺失的是下面几项。

| 需求（规格书） | 结论 |
|---|---|
| **完整历史期权链快照**（某时点全部合约的一次性全量列表） | **无单一全量接口**（`get_option_chain` 仅当前）。可用 `get_option_rank(trading_date=...)` 按排行/筛选分页近似，或按 expiry/strike 自行推演。 |
| 任意非头部合约的历史报价 | `get_option_rank` 覆盖的是"排行"（可筛选、200/页分页），排行之外的长尾合约历史 bid/ask 可能取不到；单合约历史**价格**可用 `request_history_kline` 取得。 |
| VIX / 指数行情 | 可能通过指数代码快照获取，**需实测确认**；否则需外部源。 |
| 盘中逐笔/实时推送级别数据 | 需行情权限与订阅；selector 依赖快照即可，但等级需验证。 |

### 2.3 已实测的硬约束

- **`GetOptionChain` 限流：10 次 / 30 秒**（本仓库已实测并实现滑动窗口限流）。全市场扫描不可行；规格书本身也限定"用户提供标的"。
- 每个标的的期权链需单独请求，批量分析 N 个标的耗时约 `N/10 × 30s`。
- 期权行情通常需要行情权限；权限不足会返回错误，属运行环境前置条件。

---

## 3. 关键可行性与风险点

### R1（修正）历史期权数据的真实可得性
实测可得：
- **单合约历史 K 线**：`request_history_kline(期权代码, ...)` 可用。
- **IV/HV 日序列**：`get_option_underlying_his_volatility`。
- **IV Rank / Percentile（含历史交易日）**：`get_option_underlying_rank(trading_date=...)`。
- **逐合约历史 IV / Bid-Ask / Greeks / 量仓**：`get_option_rank(trading_date=...)`（排行、200/页、可分页）。
- **期权成交量/持仓历史**：`get_option_underlying_his_statistic`、`get_option_market_statistic`。

仍不完整：**没有"某历史时点全部合约"的一次性全量链接口**，且排行之外的长尾合约历史报价可能缺失。
→ 结论：真实期权回测**基本可行**（尤其针对活跃合约），但需以排行/筛选+单合约 K 线拼装，非"一键全链快照"。**按产品决策本版本仍不做回测**，改为交易日志前向验证。

### R2（修正）IV Rank / IV Percentile 实际可得
此前"缺数据"判断**有误**。实测 `get_option_underlying_rank` 直接返回 `iv_rank`、`iv_percentile`、`iv_change`、`hv`（并可传 `trading_date` 取历史），`get_option_underlying_his_volatility` 也能自算。
→ **数据不是障碍，已确认恢复该功能**（规格书第 3.1/12.2/14/18 章已改回）。

### R3（已确认）正股腿与交易环境
- **允许正股腿**（Cash Secured Put / Covered Call / Conversion），需放开"纯期权"约束并支持正股的持仓/现金流建模。
- **仍仅限 SIMULATE-only**，不接实盘下单。
- 需注意：SIMULATE 环境下正股交割/指派行为与实盘可能不同，相关定价需标注为模拟；提前指派与股息假设需在规格中保持可配置。

### R4（中）事件日历覆盖度
`get_earnings_calendar` 仅支持**逐日/≤7 天区间**查询；`get_economic_calendar` 类似。需要缓存与调度拉取。个股"重大公告/监管消息"仍可能需要外部源。

### R5（中）流动性与可成交性
规格书要求"用真实 Bid/Ask、不能用 Mid"。SDK 提供 bid/ask/volume/OI，但**无逐笔成交/盘口深度**，滑点只能估计。可做，但应标注为估计值。

### R6（中）组合风险与相关性
风险公式（单笔/组合/回撤）是纯计算，可行；但"相关性、共同市场因子、极端行情"需要额外建模，V1.0 建议只做**名义风险 + 同标的重叠**，其余留待后续。

### R7（低）回撤 3% 的处置
规格书自述"待确定"，实现侧应做成**可配置策略（仅告警/降低新风险/停止开仓）**，不得硬编码为强制清仓。

### R8（低）数据质量与时间戳
规格书要求区分实时/延迟/历史/模拟。SDK 快照有 `update_time`，须落库并据此判定"过期/缺失"，不得把历史当实时。可做。

---

## 4. 分阶段可行性细化

### Phase 1 — 数据接入 + SQLite ｜ 可行（高）
- 现有 `opend/*` 已覆盖正股/期权链/Greeks/自选股；需新增：**SQLite 存储层**、**报价时间戳与质量检查**、每日快照落库。
- 需新增事件拉取（`get_earnings_calendar`/`get_economic_calendar`）并缓存。

### Phase 2 — 定价与策略计算 ｜ 可行（高）
- 纯数学，可离线单测（覆盖 ITM/OTM/到期）；多腿用真实 bid/ask。
- Conversion 使用正股腿（**已确认允许，SIMULATE**）；手续费可用 `order_fee_query` 或可配置常量。

### Phase 3 — 筛选与决策引擎 ｜ 可行（高）
- 趋势、HV、IV vs HV、事件、流动性、市场环境、合约筛选、NO TRADE：**可行**。
- IV Rank / IV Percentile：**已恢复纳入**（`get_option_underlying_rank` 直接提供）。
- 规则引擎（YAML）+ 标准 JSON 输出 + 状态机：与现有配置体系契合，**可行**。

### Phase 4 — 风险与持仓监控 ｜ 可行（高）
- 单笔/仓位/组合风险、Greeks 汇总（由持仓 + 期权报价计算）、止盈止损监控：可行。
- 相关性/极端情景建模：V1.0 建议简化并标注。

### Phase 5 — Dashboard ｜ 可行（高）
- 现有 Textual TUI 可扩展；也可用 Streamlit。5 个页面均为只读投影 + 人工确认，符合现有"daemon 持有 SDK、TUI 走 IPC"的架构。

### ~~Phase 6 — 回测与优化~~ ｜ 不做
- 按决策取消（R1）。注意：单合约 K 线、IV/HV 历史、IV Rank 历史、逐合约历史 IV/盘口/Greeks 其实可得，故**回测技术上基本可行**（活跃合约），只是没有一次性全量历史链。策略表现本版本仍以前向交易日志评估。

---

## 5. 建议的落地映射（复用现有架构）

```text
opend/        # SDK 访问：新增 events.py(K线/HV/日历), pricing 不在此
services/     # 新增 scanner / volatility / strategy / risk / journal 服务
domain/       # 新增 策略/合约/信号/风险 领域类型
rules/        # 新增 YAML 策略配置（第14章），配置驱动
storage/      # 新增 SQLite 层（第13章表结构）
ipc/protocol  # 新增对应请求/响应（沿用现有类型化 IPC）
tui/          # 新增 市场总览/标的分析/策略候选/持仓/日志 页面
```

- **保持** daemon 为 SDK 唯一持有者；所有计算走服务层；TUI 只做投影与人工确认（不自动下单，符合第 9 章与第 17 章）。
- 定价/风险/规则引擎为**纯函数 + 单测**，不依赖网络，便于验证与追溯（符合设计原则 10）。
- **需要放开政策**：`policy.py` / `config.py` 当前"纯期权"约束需允许正股腿，但 `allowed_trd_envs` 保持 `SIMULATE`。
- 存储层保留交易日志与信号/快照表；**不再需要回测相关表**。

---

## 6. 已确认 / 待确认事项

**已确认：**
- 不做回测（尽管历史数据部分可得，属产品选择）。
- 允许正股腿（CSP / Covered Call / Conversion）；交易环境仍仅限 **SIMULATE**。
- **恢复 IV Rank / IV Percentile**：`get_option_underlying_rank` 直接返回 `iv_rank`/`iv_percentile`（含历史交易日）。

**其他待确认（不阻塞 Phase 1–2）：**
1. **VIX/指数**：`US.VIX` 等指数快照在本账户权限下是否可读。
2. **行情权限**：当前账户的期权行情等级（决定可成交报价质量）。
3. **规格书第 18 章 TBD 参数**：是否接受"先留空 + 可配置"。

---

## 7. 结论

- **技术架构可行**，且与本仓库现有设计高度一致，可增量实现，无需重写。
- **Phase 1–5 主体全部可行**。经实测更正：**IV Rank/Percentile、IV/HV 历史、单合约历史 K 线、期权量仓历史均可获取**，此前"数据缺失"判断有误；本版本仅按产品决策不做回测，IV Rank/Percentile 已恢复纳入。
- **剩余主要风险是建模而非数据**：正股腿/指派/股息在 SIMULATE 下的精确建模，以及组合相关性的简化处理，需在实现时明确标注假设。
- **建议实施顺序**：Phase 1（数据 + 存储）→ Phase 2（纯计算 + 单测）→ Phase 3（决策引擎）→ Phase 4（风控/持仓）→ Phase 5（看板）。策略表现以前向交易日志评估，不做回测。
