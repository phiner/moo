# 美股期权交易系统开发规格书 V1.0

> 状态：草案（Draft）。本文档中的参数凡标注"待确定/待验证"的，均**不得**被实现方擅自填成看似精确的固定值。
> 可行性分析见 [`./trading-system-feasibility.md`](./trading-system-feasibility.md)。
> 目标：交给 AI Agent 进行系统设计、规则引擎开发、数据接入和交易决策看板开发。

---

## 一、系统定位与设计原则

### 1.1 系统目标

开发一套个人使用的美股期权交易决策系统。

系统不是简单的期权行情展示工具，而是一个完整的交易决策流程：

**标的输入 → 市场环境分析 → 标的筛选 → 波动率分析 → 策略匹配 → 合约筛选 → 收益风险计算 → 入场信号 → 仓位计算 → 交易管理 → 退出信号 → 交易记录 → 策略评估。**

核心任务是：

- 判断当前标的是否值得交易。
- 判断当前市场环境适合什么期权策略。
- 从真实期权链中筛选具体合约。
- 计算策略的最大收益、最大亏损、盈亏平衡点和风险收益比。
- 给出明确的入场条件、退出条件和仓位建议。
- 持续监控持仓风险。
- 记录每次交易，验证策略长期表现。

系统必须允许输出：

**NO TRADE（不交易）**

没有足够优势的交易机会时，不应该为了生成交易信号而强行推荐策略。

### 1.2 用户交易画像及约束

| 项目 | 当前设定 |
|---|---|
| 市场 | 美国股票及股票期权 |
| 可交易品种 | 股票期权 + **正股腿**（用于 Cash Secured Put / Covered Call / Conversion） |
| 交易环境 | **先仅 SIMULATE**，不接实盘下单；不做回测，不依赖历史数据 |
| 资金规模 | $50,000–$200,000 |
| 交易经验 | 有实盘期权交易经验 |
| 主要周期 | 数日至数周的波段交易 |
| 核心目标 | 收益与回撤控制兼顾 |
| 策略偏好 | 期权卖方优先 |
| 交易方式 | 用户提供标的，系统逐个分析 |
| 交易频率 | 按周分析，机会驱动，不强制交易 |
| 行情来源 | 优先使用 moomoo OpenAPI |
| 开发与部署 | 当前阶段只考虑本机开发和部署 |

### 1.3 核心设计原则

1. 卖方策略优先，但不排斥有明确优势的买方策略。
2. 优先使用风险有限的策略。
3. 不允许裸卖 Call 或裸卖 Put。
4. 不允许仅凭技术指标或单一 IV 指标决定交易。
5. 必须同时考虑正股、期权链、IV、事件和流动性。
6. 所有价格计算必须使用真实行情或明确标注的模拟数据。
7. 报价缺失、过期或不完整时，不得生成伪精确的交易建议。
8. 所有策略必须计算最大风险，不能只展示潜在收益。
9. 不允许在没有明确退出规则的情况下推荐交易。
10. 所有规则必须能够被代码执行、测试和追溯。

---

## 二、交易系统整体架构

系统采用模块化设计，避免把所有交易逻辑写在一个大型程序中。

### 2.1 模块划分

| 模块 | 主要功能 |
|---|---|
| Market Data | 正股、指数、期权链、行情快照 |
| Market Regime | 市场趋势和市场环境判断 |
| Scanner | 标的筛选 |
| Volatility Engine | IV、HV、IV Rank、IV Percentile 及 IV/HV 比较分析 |
| Event Calendar | 财报、FOMC、CPI 等事件识别 |
| Strategy Engine | 策略匹配 |
| Option Selector | 期权合约选择 |
| Pricing Engine | 策略定价和盈亏计算 |
| Risk Engine | 仓位、风险敞口和组合风险 |
| Signal Engine | 入场和退出信号 |
| Position Monitor | 持仓实时监控 |
| Journal | 交易记录 |
| Dashboard | 交易看板和人工确认 |

> V1.0 范围调整：**不做回测，不依赖历史数据。** 策略表现通过交易日志做前向评估。正股腿允许使用，但交易环境仍**仅限 SIMULATE**。IV Rank / IV Percentile 由 moomoo `get_option_underlying_rank` 直接提供（见可行性分析）。

### 2.2 数据流

```text
用户输入股票代码
        |
        v
获取正股行情和期权链
        |
        v
数据质量检查
        |
        v
市场环境分析
        |
        v
标的基本筛选
        |
        v
IV / HV / Event分析
        |
        v
策略选择引擎
        |
        v
期权合约筛选
        |
        v
收益风险计算
        |
        v
组合风险检查
        |
        v
交易信号生成
        |
        v
Dashboard展示
        |
        v
人工确认 / 执行
        |
        v
持仓监控和交易日志
```

### 2.3 数据来源原则

优先通过 moomoo OpenAPI 获取：

- 正股最新价格。
- 正股历史 K 线。
- 成交量。
- Bid / Ask。
- 期权链。
- 期权合约信息。
- 期权 Greeks。
- IV（如果接口提供）。
- 持仓及账户信息（根据 API 权限）。

其他信息，例如财报日期、FOMC、CPI、宏观事件，可以使用独立数据源。

**重要：moomoo API 是行情和账户数据来源，不等于交易系统本身。** 交易规则、交易记录、策略参数和信号结果仍然需要独立保存。

---

## 三、标的筛选模块（Scanner）

系统采用用户提供标的为主的工作模式。

例如：

```text
IREN
MSTR
NVDA
TSLA
COIN
```

系统逐个分析，而不是无条件扫描整个市场并自动交易。

可以增加 SPY、QQQ、IWM 等市场基准，用于判断整体市场环境。

### 3.1 四项核心筛选

#### A. 趋势筛选

分析：

- 日线趋势。
- 价格与 20 日、50 日均线关系。
- 均线方向。
- 近期高点和低点。
- 关键支撑和阻力。
- 成交量变化。
- 相对 SPY / QQQ 的强弱。

建议输出：

```json
{
  "trend": "bullish",
  "trend_strength": "medium",
  "above_ma20": true,
  "above_ma50": true,
  "relative_strength": "positive"
}
```

趋势标签建议：

- Strong Bullish
- Bullish
- Neutral
- Bearish
- Strong Bearish

具体计算参数待确定（V1.0 不做回测，改为前向验证）。

#### B. 波动率筛选

分析：

- 当前 IV。
- IV Rank（由 `get_option_underlying_rank` 提供）。
- IV Percentile（同上）。
- 历史波动率 HV。
- IV 与 HV 的差值（IV 相对 HV 的高低）。
- 近期期权隐含波动率变化。
- 不同到期日的 IV Term Structure。
- 不同行权价的 IV Skew。

主要判断：

- IV 是否相对偏高。
- 卖方是否获得足够的波动率补偿。
- 买方是否需要支付过高的波动率溢价。
- 财报前是否存在明显的事件溢价。

策略方向：

| 波动率状态 | 初步策略倾向 |
|---|---|
| IV 相对较高 | 优先研究信用价差 |
| IV 相对较低 | 研究 Debit Spread |
| IV 快速上升 | 评估事件风险，不盲目卖方 |
| IV 快速下降 | 评估买方期权的波动率损失 |

不能仅凭 IV 高低决定策略，还需要分析实际方向和事件风险。

#### C. 事件筛选

重点事件：

- Earnings（财报）
- FOMC
- CPI
- PPI
- NFP
- 重大监管消息
- 公司重大公告

事件必须明确：

```json
{
  "event_type": "earnings",
  "event_datetime": "2026-11-05T16:00:00",
  "event_status": "upcoming",
  "holding_over_event": true
}
```

需要区分：

- 事件前建仓。
- 事件期间持仓。
- 事件后交易。
- 事件结束后的 IV Crush。

不能把普通交易日和重大事件交易日使用完全相同的风险规则。

#### D. 流动性筛选

检查：

- 正股成交量。
- 期权成交量。
- Open Interest。
- Bid / Ask Spread。
- 报价更新时间。
- 目标合约的实际可成交性。

不能只根据理论价格选择合约。

必须使用真实可交易报价：

- 买入使用 Ask。
- 卖出使用 Bid。
- 多腿策略分别计算各腿的实际报价。
- Mid Price 仅用于参考，不能作为保证成交的价格。

---

## 四、市场环境判断（Market Regime）

市场环境是策略选择的上游条件。

建议将市场环境分为：

| 环境 | 主要特征 | 策略倾向 |
|---|---|---|
| Strong Bullish | 市场趋势强，价格持续走高 | Put Credit Spread |
| Bullish | 温和上涨 | Put Credit Spread |
| Neutral / Range | 区间震荡 | 有条件的双边信用策略 |
| Bearish | 下跌趋势 | Call Credit Spread |
| Strong Bearish | 强势下跌 | Call Credit Spread，必要时观望 |
| High Volatility | 波动剧烈、方向不明 | 减少仓位，等待确认 |
| Event Risk | 财报或宏观事件临近 | 独立事件策略模块 |

市场环境至少结合：

- SPY / QQQ 趋势。
- VIX 状态。
- 市场广度。
- 近期波动率。
- 重大事件。
- 个股相对强弱。

注意：VIX 是市场波动率参考，不等于个股 IV。

第一版可以先使用规则评分，而不是复杂机器学习模型。

---

## 五、策略库（Strategy Engine）

### 5.1 第一优先级：Credit Spread

这是系统的核心策略。

#### A. Bull Put Credit Spread

适用环境：

- 看涨或温和看涨。
- 正股趋势较强。
- IV 相对较高。
- 支撑位明确。
- 不存在无法接受的下行事件风险。

结构：

```text
Sell Higher Strike Put
Buy Lower Strike Put
Same Expiration
```

计算：

```text
Net Credit = Short Put Bid - Long Put Ask
Max Profit = Net Credit × 100
Max Loss   = (Strike Width - Net Credit) × 100
Breakeven  = Short Put Strike - Net Credit
```

#### B. Bear Call Credit Spread

适用环境：

- 看跌或温和看跌。
- 正股弱势。
- 阻力位明确。
- IV 相对较高。

结构：

```text
Sell Lower Strike Call
Buy Higher Strike Call
Same Expiration
```

计算：

```text
Net Credit = Short Call Bid - Long Call Ask
Max Profit = Net Credit × 100
Max Loss   = (Strike Width - Net Credit) × 100
Breakeven  = Short Call Strike + Net Credit
```

#### C. 初始参数建议

以下作为 V1.0 初始配置，属于待前向验证的建议值，不应视为已经证明有效的参数。

| 参数 | 初始建议 |
|---|---|
| DTE | 30–45 天 |
| Short Leg Delta | 0.15–0.25 |
| Spread Width | $2–$5 |
| Take Profit | 已实现最大信用收益的 50% |
| Stop Review | 回购成本达到初始 Credit 的 2 倍时触发复核 |
| Time Exit | 剩余 21 DTE 时评估退出 |

止损规则需要进一步明确：

如果开仓收到 $0.50 Credit，之后价差回购成本达到 $1.00，触发风险复核。

不能把这条规则简单理解为任何情况下都必须机械止损。还应检查：

- 正股是否突破关键价位。
- Short Leg Delta 是否明显恶化。
- 剩余 DTE。
- 是否发生重大事件。
- 当前组合风险。

最终执行规则应当通过前向验证逐步确定。

### 5.2 第二优先级：Cash Secured Put

适用条件：

- 用户愿意以行权价买入股票。
- 正股长期投资逻辑仍然成立。
- IV 提供足够补偿。
- 有足够现金覆盖潜在交割。

计算：

```text
Premium Received = Put Bid × 100
Cash Required    = Strike × 100
Effective Entry Price = Strike - Premium
```

需要明确区分：

- 收取权利金。
- 被指派后持有股票。
- 被指派后的股票风险。

不能把 Cash Secured Put 当作无风险收益策略。

### 5.3 第三优先级：Covered Call

适用条件：

- 已持有正股。
- 愿意在行权价卖出股票。
- 认为短期上涨空间有限。
- 收取权利金具有吸引力。

计算：

```text
Premium Received = Call Bid × 100
Effective Sale Price = Strike + Premium
```

必须将股票本身的下跌风险计入组合风险。

### 5.4 辅助策略：Debit Spread

虽然整体偏好卖方，但在方向明确、IV 不利于卖方或重大事件后，可以使用买方价差。

#### Bull Call Debit Spread

```text
Buy Lower Strike Call
Sell Higher Strike Call
Same Expiration
```

```text
Net Debit  = Long Call Ask - Short Call Bid
Max Loss   = Net Debit × 100
Max Profit = (Strike Width - Net Debit) × 100
Breakeven  = Long Strike + Net Debit
```

#### Bear Put Debit Spread

```text
Buy Higher Strike Put
Sell Lower Strike Put
Same Expiration
```

```text
Net Debit  = Long Put Ask - Short Put Bid
Max Loss   = Net Debit × 100
Max Profit = (Strike Width - Net Debit) × 100
Breakeven  = Long Strike - Net Debit
```

主要使用场景：

- 正股方向出现确认信号。
- 不想承担裸买期权的全部时间价值损耗。
- 希望把最大亏损限制在确定金额内。
- 财报或 FOMC 后 IV 回落，方向性交易机会出现。

### 5.5 明确排除的策略

V1.0 不允许：

- 裸卖 Call。
- 裸卖 Put。
- 无风险计算的多腿策略。
- 没有止损计划的无限风险策略。
- 没有真实期权链支持的精确报价推荐。

---

## 六、事件驱动交易模块（Event Strategy）

IREN 是此前重点研究的案例。

这个模块应独立于普通 Credit Spread 交易规则。

### 6.1 事件前交易

财报前通常需要分析：

- 市场预期方向。
- 预期涨跌幅。
- 当前 IV。
- IV 是否已经提前反映事件。
- 事件后 IV Crush 风险。
- 期权到期时间是否覆盖事件后的行情。

不允许仅仅因为预计财报后上涨，就直接买入高 IV Call。

### 6.2 事件后交易

之前讨论过的执行思路：

1. 不急于在消息发布前建仓。
2. 等待消息公布。
3. 观察市场第一轮反应。
4. 观察开盘后或事件后前 15–30 分钟的方向。
5. 确认价格是否突破关键高低点。
6. 结合 VWAP 判断方向是否得到确认。
7. 使用 Debit Spread 进行有限风险交易。

#### Bullish Setup

```text
IF
    Price > Opening Range High
AND Price > VWAP
AND Retest Holds
THEN
    Consider Bull Call Debit Spread
ELSE
    NO TRADE
```

#### Bearish Setup

```text
IF
    Price < Opening Range Low
AND Price < VWAP
AND Bounce Fails
THEN
    Consider Bear Put Debit Spread
ELSE
    NO TRADE
```

#### No Trade Setup

```text
IF
    Price Crosses VWAP Repeatedly
OR Direction Is Unclear
OR Bid Ask Spread Is Too Wide
THEN
    NO TRADE
```

这些条件是待验证的初始规则，不能直接假设一定有正期望值。

### 6.3 IREN 案例的已知约束

此前针对 IREN 财报周讨论过：

- 财报日期假设：2026-11-05 收盘后。
- 重点到期日：2026-11-06 和 2026-11-13。
- 曾经使用 $30 作为财报日目标价格假设。
- 曾经比较 $28 / $30 等不同执行价的 Call Debit Spread。
- 单笔最大可接受亏损：$500。

这些是具体案例中的假设和约束，不应直接变成所有标的的通用参数。

### 6.4 Long Straddle / Strangle

适用于：

- 预期大幅波动。
- 方向无法判断。
- 预期实际波动幅度超过期权已经计入的波动幅度。

必须计算：

```text
Total Premium = Call Ask + Put Ask
Upper Breakeven = Strike + Total Premium
Lower Breakeven = Strike - Total Premium
Max Loss = Total Premium × 100
```

事件前 IV 高时，买入 Straddle 可能承担很大的 IV Crush 风险。

系统不得把"波动很大"直接等同于"买入跨式可以赚钱"。

---

## 七、特殊策略研究：Conversion Arbitrage

此前讨论过持有 100 股正股，同时买入 Put、卖出 Call 的组合。

结构：

```text
Long 100 Shares
Long 1 Put
Short 1 Call
Same Strike
Same Expiration
```

如果执行价格相同，理论到期时股票与期权组合的价值为固定行权价对应的金额。

增量收益计算：

```text
Conversion PnL =
100 × (Strike - Stock Price - Put Ask + Call Bid)
- Transaction Costs
```

注意：

1. 正股使用可执行的买卖价格。
2. 买入 Put 使用 Ask。
3. 卖出 Call 使用 Bid。
4. 必须扣除佣金、费用和滑点。
5. 必须考虑提前指派、股息和资金成本。
6. 不能仅用 Mid Price 判断套利。
7. 如果已有 100 股，原始股票持仓成本不属于这笔新组合的增量套利成本。

系统可以设置一个 Arbitrage Scanner，但必须区分：

- 理论套利空间。
- 可执行套利空间。
- 扣除所有成本后的净套利空间。

只有净套利空间大于预设安全边际，才输出候选机会。

---

## 八、合约筛选模块（Option Selector）

策略引擎确定方向后，才开始选择具体期权合约。

### 8.1 输入参数

```json
{
  "symbol": "IREN",
  "strategy": "bull_put_credit_spread",
  "target_dte": [30, 45],
  "short_delta": [0.15, 0.25],
  "spread_width": [2, 5],
  "max_risk_per_trade": 500
}
```

### 8.2 合约筛选规则

筛选：

- 到期日。
- Strike。
- Delta。
- Gamma。
- Theta。
- Vega。
- IV。
- Bid。
- Ask。
- Volume。
- Open Interest。
- Bid/Ask Spread。

对每个候选组合计算：

- 净 Credit 或 Debit。
- 最大盈利。
- 最大亏损。
- 盈亏平衡点。
- 风险收益比。
- 每张合约占用资金。
- 预期持仓周期。
- 距离关键支撑和阻力的空间。

### 8.3 期权报价质量检查

每条报价至少保存：

```json
{
  "symbol": "IREN",
  "expiration": "2026-10-30",
  "strike": 26,
  "option_type": "put",
  "bid": 0.50,
  "ask": 0.53,
  "last": 0.52,
  "delta": -0.32,
  "gamma": 0.13,
  "iv": 1.395,
  "volume": 1000,
  "open_interest": 5000,
  "quote_timestamp": "2026-10-28T12:00:00-04:00"
}
```

上面只是数据结构示例，不代表真实行情。

如果没有可靠的报价时间戳，不能将报价视为实时数据。

---

## 九、入场规则（Entry Engine）

系统必须区分：

- 观察信号。
- 候选交易。
- 已确认交易。
- 交易失效。

每笔交易都要有明确的入场条件。

示例：

```json
{
  "entry_conditions": [
    "market_regime_is_bullish",
    "underlying_above_vwap",
    "support_is_holding",
    "iv_is_attractive",
    "option_liquidity_passed",
    "portfolio_risk_passed"
  ],
  "entry_status": "pending_confirmation"
}
```

入场信号不能仅靠评分达到某个分数就自动执行。

建议采用两层机制：

**第一层：量化筛选** —— 判断机会是否满足基本条件。

**第二层：交易确认** —— 检查价格行为、关键技术位、报价质量及组合风险。

V1.0 默认只产生建议，不自动下单。

---

## 十、风险管理模块（Risk Engine）

风险管理是整个系统最重要的模块。

### 10.1 单笔风险

此前讨论的初始建议：

```text
Risk Per Trade = Account Equity × 0.25%
```

例如：

| 账户资金 | 0.25% 单笔风险 |
|---|---:|
| $50,000 | $125 |
| $100,000 | $250 |
| $200,000 | $500 |

这里的风险指策略最大可能亏损，不是投入的权利金或保证金。

实际风险还应受用户为具体交易设定的绝对金额上限约束：

```text
Allowed Risk = MIN(Equity × Risk Percentage, User Defined Max Risk)
```

例如 IREN 财报交易此前设定的 $500 单笔最大亏损，应作为该案例的额外限制。

### 10.2 仓位计算

对于 Credit Spread：

```text
Risk Per Contract = (Spread Width - Net Credit) × 100
```

对于 Debit Spread：

```text
Risk Per Contract = Net Debit × 100
```

张数：

```text
Contracts = FLOOR(Allowed Risk / Risk Per Contract)
```

如果计算结果小于 1，输出：

```text
NO TRADE - Minimum Contract Exceeds Risk Budget
```

不能为了凑仓位突破风险限制。

### 10.3 组合风险

初始建议参数：

| 风控项目 | 初始值 |
|---|---:|
| 单笔初始风险 | 账户资金 0.25% |
| 组合最大风险 | 账户资金 2% |
| 单日亏损限制 | 账户资金 1% |
| 账户回撤警戒线 | 3% |

以上均为待验证的初始风险参数。

必须进一步区分：

- 已实现亏损。
- 未实现亏损。
- 到期最大可能亏损。
- 当前市场风险。
- 相关性风险。
- 同一标的多笔交易的风险。

组合最大风险不能简单地把不同策略的名义风险相加后就认为风险已经充分衡量，还需要考虑标的相关性、共同市场因子和极端行情。

### 10.4 风险触发动作

建议规则：

```text
IF Daily Loss >= 1% Equity:        Block New Entries
IF Portfolio Open Risk >= 2% Equity: Block New Positions
IF Drawdown >= 3%:                  Enter Risk Review Mode; Reduce New Trade Risk
```

3% 回撤对应的具体操作还需要进一步确定，不能在没有验证的情况下直接设为强制清仓。

---

## 十一、退出管理（Exit Engine）

所有交易必须同时具备盈利退出、亏损退出和时间退出规则。

### 11.1 Credit Spread

初始规则：

- 获得最大可实现信用收益的 50% 时考虑止盈。
- 回购成本达到初始 Credit 的 2 倍时触发止损复核。
- 剩余 21 DTE 时重新评估。
- 正股突破关键技术位时重新评估。
- Short Leg Delta 显著增加时重新评估。
- 重大事件风险突然出现时重新评估。

### 11.2 Debit Spread

必须记录：

- 最大亏损。
- 目标盈利。
- 价格失效位。
- 事件后 IV 变化。
- 时间价值损耗。
- 剩余 DTE。

不能只依靠期权价格百分比止损。

### 11.3 所有退出规则

```json
{
  "exit_rules": {
    "take_profit": "configurable",
    "stop_loss": "configurable",
    "time_exit": "configurable",
    "technical_invalidation": true,
    "event_risk_exit": true
  }
}
```

每次退出必须记录触发原因。

---

## 十二、交易看板（Dashboard）

看板应该围绕交易决策，而不是单纯展示大量行情。

### 12.1 首页：市场总览

- SPY / QQQ / IWM。
- VIX。
- 市场环境。
- 今日重大事件。
- 市场风险状态。
- 当前持仓风险。

### 12.2 标的分析页

- 正股价格。
- 日线趋势。
- VWAP。
- 支撑阻力。
- 成交量。
- IV / HV。
- IV Rank / IV Percentile。
- 财报日期。
- 当前策略建议。

### 12.3 策略候选页

每个标的展示最多若干个经过筛选的候选策略。

| 项目 | 内容 |
|---|---|
| 标的 | IREN |
| 市场判断 | Bullish / Bearish / Neutral |
| 策略 | Put Credit Spread |
| 到期日 | 实际候选日期 |
| 短腿 | Strike / Delta / Bid |
| 长腿 | Strike / Ask |
| 净权利金 | 实际计算 |
| 最大盈利 | 实际计算 |
| 最大亏损 | 实际计算 |
| 盈亏平衡 | 实际计算 |
| 建议张数 | 风险预算计算 |
| 入场条件 | 明确规则 |
| 退出条件 | 明确规则 |
| 信号状态 | Pending / Ready / Invalid |

### 12.4 持仓管理页

- 当前持仓。
- 当前市值。
- 未实现盈亏。
- Delta / Gamma / Theta / Vega 敞口。
- 到期日。
- Short Strike 距离。
- 最大潜在亏损。
- 组合总风险。
- 退出信号。

### 12.5 交易日志页

- 交易日期、标的、策略类型、交易方向、期权合约。
- 开仓价格、平仓价格。
- 开仓理由、退出理由。
- 最大盈利、最大亏损、实际盈亏。
- 持仓时间。
- 入场时 IV、退出时 IV。
- 是否按规则执行。

---

## 十三、数据存储与技术实现

### 13.1 为什么仍然需要数据库

moomoo API 负责提供行情和账户数据，但不能替代交易系统的数据存储。系统仍然需要保存：

- 每日行情快照。
- 历史期权链快照。
- 交易信号。
- 策略参数。
- 用户确认记录。
- 持仓变化。
- 交易日志。
- 风险事件。

否则无法准确回答：某个策略过去表现如何？当时为什么产生这个信号？开仓时的 IV 是多少？为什么止损？参数调整前后有什么变化？

### 13.2 本机开发架构建议

```text
Local Computer
│
├── Data Layer
│   ├── Moomoo OpenAPI
│   ├── Market Data
│   └── Event Data
│
├── Backend
│   ├── Python
│   ├── Strategy Engine
│   ├── Risk Engine
│   ├── Pricing Engine
│   └── Signal Engine
│
├── Storage
│   ├── SQLite
│   ├── Historical Snapshots
│   └── Trade Journal
│
└── Frontend
    ├── Dashboard
    ├── Scanner
    ├── Strategy Analysis
    └── Position Monitor
```

建议第一版采用：Python + moomoo OpenAPI + SQLite + Streamlit 或 Web 前端 + JSON/YAML 配置。初期不需要复杂云端部署或分布式数据库。

### 13.3 数据层设计

至少需要以下逻辑数据表：

| 表 | 用途 |
|---|---|
| symbols | 股票标的 |
| stock_quotes | 正股行情 |
| option_quotes | 期权行情 |
| option_contracts | 期权合约信息 |
| market_snapshots | 市场环境快照 |
| events | 事件日历 |
| strategy_configs | 策略参数 |
| trade_candidates | 策略候选 |
| trade_signals | 交易信号 |
| positions | 当前持仓 |
| orders | 订单记录 |
| trades | 已完成交易 |
| risk_snapshots | 风险快照 |

行情数据应当带时间戳，并区分实时、延迟、历史和模拟数据。

---

## 十四、规则引擎设计

这是交给 AI Agent 最重要的部分。不要把策略规则直接写死在代码中，建议采用配置驱动的规则引擎。例如：

```yaml
strategy:
  name: bull_put_credit_spread
  enabled: true

  market_conditions:
    allowed_regimes:
      - bullish
      - strong_bullish

  volatility:
    iv_rank_min: null
    iv_rank_max: null
    iv_percentile_min: null

  expiration:
    min_dte: 30
    max_dte: 45

  short_leg:
    delta_min: 0.15
    delta_max: 0.25

  spread:
    min_width: 2
    max_width: 5

  exit:
    take_profit_pct: 0.50
    stop_review_multiple: 2.0
    time_exit_dte: 21

  risk:
    max_account_risk_pct: 0.25
```

其中 `null` 表示尚未确定，不允许 Agent 擅自补成看似精确的数值。

### 14.1 决策引擎输出格式

每次分析都应生成标准 JSON：

```json
{
  "symbol": "IREN",
  "analysis_timestamp": "2026-11-08T20:00:00-05:00",
  "data_quality": "valid",
  "market_regime": "bullish",
  "volatility_regime": "high",
  "event_risk": "medium",
  "recommended_action": "consider_bull_put_credit_spread",
  "trade_status": "candidate",
  "strategy": {
    "type": "bull_put_credit_spread",
    "expiration": null,
    "short_strike": null,
    "long_strike": null,
    "net_credit": null,
    "max_profit": null,
    "max_loss": null,
    "breakeven": null
  },
  "risk": {
    "allowed_risk": null,
    "recommended_contracts": null,
    "portfolio_risk_passed": false
  },
  "entry_conditions": [],
  "exit_conditions": [],
  "rejection_reasons": [],
  "missing_data": []
}
```

这只是输出协议示例，实际合约和价格必须由行情数据计算。

### 14.2 交易状态机

```text
SCANNED → ANALYZED → CANDIDATE → PENDING_CONFIRMATION → READY → APPROVED
        → OPEN → MONITORING → EXIT_SIGNAL → CLOSED
```

任何阶段如果数据失效或条件不满足，可以进入：`REJECTED` / `INVALIDATED` / `EXPIRED`。必须保存状态变化和对应原因。

---

## 十五、策略验证（前向）

**V1.0 不做回测，不依赖历史期权数据。** 系统不因规则看起来合理就认定策略有效，改为**前向验证**：

- 通过交易日志（第十二章 12.5）持续记录每笔交易的入场/退出、理由、当时 IV 与实际盈亏。
- 以固定周期（如按周/按月）汇总真实成交与模拟成交的表现。

### 核心绩效指标（基于交易日志前向统计）

| 指标 | 说明 |
|---|---|
| Win Rate | 胜率 |
| Average Win | 平均盈利 |
| Average Loss | 平均亏损 |
| Profit Factor | 盈利因子 |
| Expectancy | 单笔期望收益 |
| Max Drawdown | 最大回撤（按日志累计） |
| Return on Risk | 风险资本收益率 |
| Average Holding Period | 平均持仓时间 |

尤其需要关注：**胜率高不代表策略好。** 信用价差可能有很高胜率，但少数几次大亏损就可能抵消大量小额盈利。

> 说明：由于不做回测、且不获取历史期权数据，本版本**不提供历史重现能力**。绩效结论仅来自上线后的前向记录。

---

## 十六、AI Agent 开发任务说明（Phase 1–5）

### Phase 1：数据接入与基础设施

1. 接入 moomoo OpenAPI。2. 获取正股行情。3. 获取期权链。4. 获取 Greeks 和 IV（以接口实际支持为准）。5. 建立报价时间戳和数据质量检查。6. 建立 SQLite 数据库。7. 实现股票和期权数据查询。

验收：能查询指定股票与期权链；能识别报价过期和数据缺失；不会把历史报价标记成实时行情。

### Phase 2：定价与策略计算

1. Put Credit Spread。2. Call Credit Spread。3. Cash Secured Put。4. Covered Call。5. Bull Call Debit Spread。6. Bear Put Debit Spread。7. Conversion 计算。

验收：最大收益/最大亏损/盈亏平衡正确；多腿使用真实可执行方向的 Bid/Ask；手续费与滑点可配置；单元测试覆盖价内、价外、到期情景。

### Phase 3：筛选与决策引擎

1. 趋势判断。2. 波动率分析。3. 事件识别。4. 市场环境判断。5. 策略匹配。6. 合约筛选。7. NO TRADE 逻辑。

验收：给定代码，可输出市场状态、波动率状态、事件风险、可选策略、候选合约、收益风险计算、不交易的具体理由。

### Phase 4：风险管理与持仓监控

1. 单笔风险计算。2. 组合风险计算。3. 仓位建议。4. 止盈止损监控。5. 账户回撤监控。6. 持仓 Greeks 汇总。

验收：任何候选交易都必须先通过风险检查。

### Phase 5：Dashboard

市场总览、标的分析、策略候选、持仓管理、交易日志页面。

验收：用户能从输入股票代码开始，完成完整分析和人工交易确认。

> Phase 1–5 之外不再设"回测/优化"阶段；策略参数调整通过规则配置文件（第十四章）版本管理，效果以前向交易日志评估。

---

## 十七、V1.0 暂不开发的功能

自动实盘下单；自动组合调仓；多账户管理；云端部署；复杂机器学习预测；高频交易；全市场自动扫描；自动策略参数优化。

此外，本版本**明确不做**：

- 回测（改为前向验证，见第十五章）；虽然 moomoo 可提供部分历史期权数据，本版本不将其用于回测。

第一版的核心是：**行情准确、策略计算正确、风险控制可靠、交易建议可解释。**

---

## 十八、需要进一步确认的参数

以下参数尚未确定，开发时必须保留为可配置项。

| 参数 | 当前状态 |
|---|---|
| IV Rank 最低要求 | 待确定 |
| IV Percentile 门槛 | 待确定 |
| IV / HV 比较门槛 | 待确定 |
| 最低期权成交量 | 待确定 |
| 最低 Open Interest | 待确定 |
| 最大 Bid/Ask Spread | 待确定 |
| Credit Spread 最低风险收益比 | 待确定 |
| 不同策略的市场环境权重 | 待验证 |
| Delta 最佳区间 | 初始 0.15–0.25，待验证 |
| 50% 止盈规则 | 初始建议，待验证 |
| 2 倍 Credit 止损复核 | 初始建议，待验证 |
| 21 DTE 时间退出 | 初始建议，待验证 |
| 组合风险 2% | 初始建议，待验证 |
| 3% 回撤后的具体操作 | 待确定 |
| 事件前是否允许卖方建仓 | 按事件风险分类决定 |
| 事件后等待时间 | 初始观察 15–30 分钟，待验证 |

Agent 不得自行将这些空缺填入未经确认的固定值。

---

## 十九、最终开发目标

用户输入：

```text
IREN
MSTR
NVDA
TSLA
```

系统输出：

```text
1. 市场环境                Bullish / Bearish / Neutral
2. 标的状态                趋势、波动率、流动性、事件风险
3. 策略建议                Put/Call Credit Spread, CSP, Covered Call, Debit Spread, NO TRADE
4. 合约选择                到期日、行权价、Delta、Bid、Ask
5. 盈亏计算                Net Credit/Debit, Max Profit, Max Loss, Breakeven
6. 风险管理                单笔风险、推荐张数、组合风险、风险敞口
7. 交易计划                入场条件、失效条件、止盈条件、止损条件、时间退出
8. 后续管理                持仓监控、风险预警、交易日志、策略绩效
```

**最终定位：它是一套以规则为核心、以真实期权链为依据、以风险管理为约束、以人工决策为最终确认的美股期权交易系统。**
