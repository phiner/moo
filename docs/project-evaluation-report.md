# mooc 项目评估报告（供外部 AI 评审）

- 文档目的：汇总当前项目的总体规划与目标、已完成与未完成功能/能力现状，供另一 AI 进行评估与后续规划参考。
- 报告基准：仓库当前工作区快照（`main`，工作树干净，最近提交见文末），代码与文档事实为准；不包含运行时外部依赖（OpenD/真实行情权限）下的实时验证结果。
- 生成日期：2026-11-11
- 项目路径：`/home/phiner/projects/mooc`

---

## 1. 项目概述与总体目标

### 1.1 定位
`mooc` 是一套面向个人使用的**美股期权交易决策系统**（不是简单行情展示工具）。系统目标是覆盖完整决策链路：

**标的输入 → 市场环境分析 → 标的筛选 → 波动率分析 → 策略匹配 → 合约筛选 → 收益风险计算 → 入场信号 → 仓位计算 → 交易管理 → 退出信号 → 交易记录 → 策略评估**。

核心要求：
- 判断标的是否值得交易、当前环境适合何种策略、从真实期权链筛选具体合约并计算收益/风险。
- 给出明确的入场/退出条件与仓位建议，持续监控持仓风险，记录交易并验证策略表现。
- **必须允许输出 `NO TRADE`**；无足够优势时不得强行给出交易信号。
- 第一版核心：**行情准确、策略计算正确、风险控制可靠、交易建议可解释**（以人工确认为最终决策）。

### 1.2 用户画像与硬约束（规划约束）
- 市场：美股及股票期权；可交易品种含期权与**正股腿**（CSP/Covered Call/Conversion 等场景），但交易环境**仅 SIMULATE**（不接实盘下单）。
- 资金规模 $50k–$200k；数日至数周波段、按周机会驱动；卖方策略优先，不排斥有明确优势的买方策略。
- 优先使用风险有限策略；**禁止裸卖 Call/Put、无限风险且无明确退出规则的策略**；无真实期权链/报价不完整时不得生成伪精确建议。
- 行情/账户来源优先 moomoo OpenAPI；交易规则、信号、参数与记录需独立保存。
- 不做回测、不依赖历史期权数据做历史重现；策略表现通过**前向交易日志**评估（V1.0 范围调整）。
- 仅本机开发与部署。

### 1.3 技术架构与总体设计
- **架构**：Daemon-mediated —— `OpenD <- moomoo-api (SDK) -> daemon <- typed IPC (Unix socket) -> TUI/CLI`。
  - `daemon`：SDK 连接唯一持有者；解码类型化 IPC 请求、分发到服务、编码响应；SDK 调用串行化（锁）以规避单 context 并发不确定性。
  - `TUI/CLI`：投影与交互层；变更通过 IPC 请求/命令触发；默认只产生建议、不自动下单。
- **实现栈**：Python（`>=3.11`），`moomoo-api`、`pydantic`、`pyyaml`；可选 `textual`（TUI）；开发工具 `pytest/mypy/ruff`；存储 SQLite；配置 TOML + `MOOC_*` 环境变量覆盖。
- **配置与策略**：`mooc.toml`/`mooc.example.toml`；策略规则以 YAML 放于 `rules/`（配置驱动，`null` 表示未确定参数，Agent/实现不得擅自虚构）；`[trading]` 策略为 SIMULATE-only。
- **代码组织（主要）**：`opend/`（SDK 访问）、`services/`（业务逻辑：分析/定价/风控/扫描/选约/记录/监控/行情/交易等）、`domain/`（领域类型）、`storage/`（SQLite schema/db/repo）、`ipc/`（协议与客户端）、`daemon/`（生命周期与服务端）、`tui/`（终端界面）、`rules/`（策略配置）。

---

## 2. 规划与路线图（目标态）

### 2.1 规格书阶段目标（Phase 1–5）
依据 `docs/trading-system-spec-v1.md`：
- **Phase 1 数据接入与基础设施**：接入 moomoo OpenAPI，正股/期权链/Greeks/IV（按接口能力），报价时间戳与数据质量检查，SQLite，股票与期权数据查询。
- **Phase 2 定价与策略计算**：Put/Call Credit Spread、Cash Secured Put、Covered Call、Bull Call/Bear Put Debit Spread、Conversion 计算；多腿真实 Bid/Ask；手续费/滑点可配置；单测覆盖 ITM/OTM/到期等。
- **Phase 3 筛选与决策引擎**：趋势、波动率、事件识别、市场环境、策略匹配、合约筛选、`NO TRADE`；标准决策输出与状态机语义。
- **Phase 4 风险管理与持仓监控**：单笔/组合风险、仓位建议、止盈止损监控、回撤监控、持仓 Greeks 汇总；候选须先过风控。
- **Phase 5 Dashboard**：市场总览、标的分析、策略候选、持仓管理、交易日志；支持从输入代码到分析与人工确认的完整流程。

### 2.2 明确不在 V1.0 的范围（规划层面）
- 自动实盘下单、自动组合调仓、多账户管理、云端部署、复杂 ML 预测、高频/全市场自动扫描、自动策略参数优化。
- **回测**（改为前向验证）；虽部分历史数据可得，但本版本不用于回测。

### 2.3 可行性结论摘要（来自 `docs/trading-system-feasibility.md`）
- Phase 1–5 主体总体可行；现有 daemon/IPC/TUI 架构可增量扩展。
- 已实测/更正：IV Rank/Percentile、IV/HV 历史、单合约历史 K 线、逐合约历史 IV/盘口/Greeks/量仓等可获取；但无“某历史时点全量链一次性接口”，且长尾合约历史可能缺失。VIX 指数快照不可直接可靠读取（需替代指标或显式缺失）。
- 主要风险偏建模与产品约束：正股腿/指派/股息在 SIMULATE 下的精确建模、组合相关性简化、`GetOptionChain` 限流（10 次/30 秒）等。

### 2.4 README 当前状态标记（仓库自述）
- 已标记完成/进行中语义：S0、S1、Watchlist、S2（trade 只读）、Analysis+Journal、Storage、Recording+monitoring。
- 待办：`S3 trade (simulated orders)`、`S4 screeners / ranks / events`。

---

## 3. 已完成功能/能力（按模块与可观测交付）

> 说明：“已完成”指代码/接口/页面已落地且有对应实现与（多数）测试覆盖；不等同于已在真实行情环境完成端到端验收（live 测试需 OpenD 且环境具备权限）。

### 3.1 基础设施与运行形态
- **CLI 入口**（`mooc.cli`）：`doctor`、`probe` 子命令集、`daemon run/status/stop`、`tui`；统一配置加载与错误处理。
- **守护进程**：后台启动/日志（`~/.mooc/mooc.log` 或运行目录）、PID/socket 管理与存活检测（`daemon/lifecycle.py`、`daemon/server.py`）。
- **类型化 IPC**：请求/响应协议（`ipc/protocol.py`，Pydantic 模型、判别式 `kind`、帧大小上限、leg 校验等）；客户端（`ipc/client.py`）；daemon 按请求类型分发至 option/market/trade/watchlist 等服务。
- **连接与策略约束**：OpenD 客户端封装（`opend/client.py` 等）、交易环境策略解析（`policy.resolve_trd_env`，默认 SIMULATE 策略）、配置校验失败快速报错。
- **校验脚本**：`scripts/validate.sh` 执行 `ruff check`、`ruff format --check`、`mypy`、`pytest -q -m "not live"`。

### 3.2 数据接入（OpenD/SDK 访问层）
- **期权**：到期日、期权链、组合分析（`opend/option.py`）。
- **行情与快照**：股票/期权快照与新鲜度判定（`opend/quote.py`、`services` 侧 freshness 处理）；历史 K 线、波动率相关数据（`opend/market.py`、`opend/volatility.py`）。
- **事件**：财报/（可选）经济日历获取与映射（`opend/events.py`）。
- **自选股**：分组、成员与摘要能力（`opend/watchlist.py`、`services/option_data.py`/watchlist 相关流程）。
- **交易只读**：账户、资金、持仓、订单查询（`opend/trade.py`、`services/trade.py`）；显式按 SIMULATE 策略约束。

### 3.3 领域建模与纯计算服务
- **定价**（`services/pricing.py`）：信用/借记价差等策略的最大盈亏、盈亏平衡等计算（多腿 Bid/Ask 方向语义在实现中体现）；配套单测覆盖多场景（`tests/test_pricing.py`）。
- **波动率分析**（`services/volatility.py`）：IV/HV、IV Rank、IV Percentile 等汇总（数据来源于 OpenD 接口能力）。
- **扫描与筛选**（`services/scanner.py`）：趋势/波动率/事件等维度的扫描结果结构化（含 `NO TRADE` 相关输入缺失与风险信号表达）。
- **合约选择**（`services/selector.py`）：按规则与候选报价筛选价差组合（DTE/Delta/宽度等），支持可解释的未选中原因（实现层面）。
- **决策引擎**（`services/decision.py`、`services/analyze.py`）：生成标准化决策输出（14.1 语义字段：市场/波动率/事件状态、推荐动作、交易状态、策略与风险块、缺失数据与拒绝原因等）；在可得输入下补全策略定价与风险评估。
- **风险引擎**（`services/risk.py`、`domain/risk.py`）：单笔风险/合约数评估（需 equity 与风险预算等可验证输入，否则不放行）、Greeks 聚合、退出信号、回撤策略动作枚举等纯逻辑能力。
- **规则加载**（`services/rules.py`）：从 `rules/` 加载 YAML 策略配置。
- **日志绩效**（`services/journal.py`）：基于交易日志条目计算前向绩效指标（胜率、盈亏因子、期望、回撤、持有期等）。

### 3.4 分析主链路与持久化
- **分析服务/IPC**：`GetAnalysis`（按 `code`）经 `MarketDataService` 调用 `analyze_symbol`，返回 `AnalysisResult.output`（决策字典）；同时 best-effort 将决策记录落库（`services/recording.py` → candidates/signals/risk_snapshots）。
- **CLI 分析**：`probe analyze <code> [--acc-id N] [--json]`；在提供 `--acc-id` 时可尝试拉取资金用于风险 sizing（实现见 `cli.py`），并在本地 best-effort 记录。
- **存储层**：SQLite schema v2（`storage/schema.py`、`storage/db.py`）包含 `symbols`、`stock_quotes`、`option_contracts`、`option_quotes`、`events`、`trade_candidates`、`trade_signals`、`risk_snapshots`、`trade_journal`、`confirmations` 等及索引；`storage/repo.py` 提供 upsert/查询与部分写入（含决策记录幂等检查、journal/confirmations CRUD 等）。
- **日记查询**：`GetJournal` IPC 与 `probe journal` CLI 基于存储日志输出绩效报告。

### 3.5 监控能力（当前形态）
- **CLI 监控**：`probe monitor --acc-id N [--trd-env] [--code] [--currency] [--json]` 拉取持仓与期权快照，按**单腿近似**计算平仓成本与退出信号（take-profit/stop-review/time-exit，受首条启用规则阈值影响）；对过期报价抑制价格信号并标注（`monitor_note: single-leg approximation` 等）。该逻辑当前主要在 CLI 侧编排，**未作为 daemon/IPC 的统一 `GetMonitor` 服务暴露**。

### 3.6 TUI（Dashboard 投影）
- Textual TUI（`mooc tui`）已提供多标签页工作流（README/实现体现）：Watchlist、Chain、Strategy、Account、Orders、Analysis、Journal 等；自选组逐行加载期权摘要并受限流节奏约束，支持从 watchlist 行跳转链路分析等交互（以实际 `tui/app.py` 为准）。

### 3.7 测试与质量保障现状（可观测）
- 测试覆盖面广（`tests/` 含 analyze/decision/pricing/risk/rules/scanner/selector/storage/IPC/daemon/CLI/TUI/market/trade/watchlist/recording_monitor 等，另有 `*_live.py` 标记 live）。
- 存在统一校验入口 `scripts/validate.sh`；本报告生成环境未执行全量校验（亦不依赖 OpenD），故**不在此断言当前全绿状态**，仅说明校验流程已定义。

---

## 4. 未完成功能/能力（与规划差距）

### 4.1 路线图明确未完成
- **S3 trade (simulated orders)**：未实现模拟下单/撤单等写操作链路（当前 trade 为只读查询）。
- **S4 screeners / ranks / events**：未实现面向筛选/排名/事件驱动的系统化能力与对应产品化入口（超出当前 probe/TUI 已有范围）。

### 4.2 规格书 Phase 目标的主要缺口（按能力域）
- **Phase 1**：虽已有查询与质量标记基础，但“每日快照落库/历史快照体系”的完整性、覆盖面与可回放性仍有增强空间（例如分析/行情关键输入的统一留痕策略需持续收敛）。
- **Phase 2**：已覆盖多种价差与部分策略计算，但规格要求的 **Cash Secured Put / Covered Call / Conversion（含正股腿与成本/指派/股息等假设）** 的产品化闭环、费用/滑点配置化与验收口径仍需对照规格逐项补齐与标注假设。
- **Phase 3**：`NO TRADE` 与结构化输出已具备基础，但**策略匹配广度**（多策略/多候选并列、事件驱动独立策略模块、市场环境更完整建模）、**入场/退出条件生成的可执行性与完备性**、以及**状态机全生命周期落地**（SCANNED→…→CLOSED 及 INVALIDATED/EXPIRED 等持久化与流转）仍未完全达到规格终态。
- **Phase 4**：单笔风控与基础退出信号已存在，但**组合级风险（相关性/同标的叠加/敞口上限的系统化聚合）**、**持仓 Greeks/敞口在账户与组合维度的完整监控闭环**、回撤触发后的标准化处置与可观测性仍需增强；监控能力目前以 CLI 单腿近似为主，**daemon/IPC/TUI 统一监控服务与组合聚合**尚未产品化。
- **Phase 5**：TUI 已有多页面雏形，但与规格 12.x 的“完整决策看板”（市场总览含基准/VIX 替代与风险状态、策略候选对比、持仓页组合风险/Greeks/距离短腿/退出信号联动、交易确认与状态流转等）仍存在差距；**从输入到人工确认的闭环**在无下单能力前提下需更明确的确认/记录语义。

### 4.3 已知设计/实现缺口与待收敛点（基于当前代码与文档）
- **分析风控输入一致性**：`GetAnalysis` IPC 当前仅含 `code`，daemon 路径未注入账户权益用于 sizing；CLI `probe analyze` 可选 `--acc-id` 走本地资金查询（能力存在但链路未统一）。
- **市场环境（Regime）**：分析与扫描中市场/趋势判断以可得数据为基础；VIX 快照不可用已在可行性文档记录，需稳定的替代口径与显式缺失标注（实现需持续对齐）。
- **决策落库与回查**：写入为 best-effort 且幂等键依赖 `(symbol,strategy,created_at)`；`repo` 侧面向回查的列表查询与对外查询入口（CLI/IPC）相对有限，运维/评估可观测性可提升。
- **快照/事件留痕**：服务层对“分析当时关键输入快照”的持久化策略尚可进一步系统化（在不破坏 opend 层纯取数的前提下于 service 层补齐）。
- **监控聚合**：多腿组合识别、净权利金/净平仓成本、组合 Greeks 与最大敞口估计、以及“过期/缺价不出信号”的统一服务化尚未落地。
- **规格第 18 章 TBD 参数**：IV Rank/Percentile/IV-HV 门槛、流动性阈值、风险收益比、退出参数细化、回撤处置等仍需配置化与前向验证，不应硬编码。

### 4.4 风险与外部依赖限制
- 强依赖 OpenD 运行状态与行情/交易权限；限流（如期权链 10/30s）约束批量分析体验。
- SIMULATE 环境与实盘在交割/指派等行为上可能存在差异，涉及正股腿策略时需持续标注假设。
- 组合相关性与极端情景在 V1.0 规划中倾向简化建模，评估时应将其视为已知方法学边界。

---

## 5. 评估建议关注点（供评审 AI 使用）

1. **目标一致性**：已实现能力是否支撑“可解释、风险优先、允许 NO TRADE、人工确认”的核心定位；哪些偏离或尚未闭环。
2. **正确性与可验证性**：定价/风控/选约/决策输出的边界条件（缺报价、stale、缺 equity、规则参数未确定）处理是否保守且可解释；测试覆盖是否匹配关键风险路径。
3. **数据质量与可追溯性**：报价时间戳/来源/缺失字段标记、决策与快照/事件的留痕、日志前向评估所需字段是否完备。
4. **架构与演进性**：daemon 单连接、串行化、IPC 协议演进、服务分层是否便于后续补齐 S3/S4 与 Phase 3–5 缺口。
5. **范围控制**：是否存在超出 SIMULATE-only/不自动下单/不做回测等约束的实现风险；TBD 参数是否保持可配置且未被“默认真值化”。

---

## 6. 参考资料与基线

- `README.md` — 产品概览、命令、状态标记与使用说明
- `docs/trading-system-spec-v1.md` — 目标交易系统开发规格书 V1.0（Draft）
- `docs/trading-system-feasibility.md` — 可行性分析与实测结论
- `mooc.example.toml`、`rules/bull_put_credit_spread.yaml` — 配置与示例策略
- `scripts/validate.sh`、`pyproject.toml` — 质量门禁与工程配置
- 最近提交（截至报告时）：
  - `6b3cfc7 fix(mooc): harden decision recording and position monitoring`
  - `944c410 feat(mooc): persist analysis decisions and add position monitor`
  - `8a625e1 feat(mooc): TUI analysis/journal pages + journal IPC (Phase 5)`

*本报告为静态评估材料，建议结合 `scripts/validate.sh` 结果、目标环境下的 `mooc doctor`/live 测试与实际 OpenD 权限情况进行最终验收评估。*
