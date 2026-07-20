# Weekly Performance Log: NexusTrader Algorithmic Operations
**Reporting Period:** July 13, 2026 to July 20, 2026  
**System Status:** ACTIVE 🟢  
> [!WARNING]
> **Operational Status:** `LIVE CAPITAL TRADING (REAL MONEY)`  
> **WARNING:** The system is currently executing live transactions with real capital via broker API credentials. Real financial assets are at risk.


Welcome to the weekly performance report of **NexusTrader**, a self-learning quantitative trading bot driven by an ensemble of technical strategies and optimized in real-time by a Policy Gradient Neural Network.

Below is an extensive breakdown of the system's performance, resource allocations, neural network adaptations, and trading diagnostics.

---

## 📊 Executive Portfolio Summary

| Metric | Value |
| :--- | :--- |
| **Current Account Equity** | **€5.80** |
| **Starting Balance (Week Start)** | €6.04 |
| **Net PnL (Euros)** | **€-0.24** |
| **Weekly Return (%)** | **-3.99%** |
| **Risk Profile Configuration** | `AGGRESSIVE` |
| **Active Trade Count** | 10 |
| **Overall System Win Rate** | **10.0%** |
| **Profit Factor** | **0.03** |

---

## 💼 Portfolio Asset Performance Breakdown
Performance metrics segmented by individual portfolio asset ticker:

| Asset Ticker | Trades Executed | Win Rate | Net Asset PnL |
| :--- | :--- | :--- | :--- |
| ADA-USD | 2 | 0.0% | €-0.06 |
| BTC-USD | 1 | 0.0% | €-0.00 |
| DOGE-USD | 2 | 0.0% | €-0.05 |
| DOT-USD | 2 | 50.0% | €-0.04 |
| ETH-USD | 2 | 0.0% | €-0.05 |
| LINK-USD | 1 | 0.0% | €-0.04 |


---

## 🧠 Neural Policy Network Allocations
The Policy Gradient Neural Network dynamically distributes weights among individual strategies on each tick. It monitors indicators (OU market regime parameters, RSI, Bollinger position, ATR volatility, and win rate trend) to shift allocations toward strategies that perform best in current conditions.

Current baseline weights computed by the neural network:

| Strategy | Allocation Weight | Visual Distribution |
| :--- | :--- | :--- |
| **EMA Crossover** | 6.5% | `████████░░░░░░░` |
| **RSI Reversion** | 7.7% | `██████████░░░░░` |
| **BB Breakout** | 9.1% | `███████████░░░░` |
| **ML Random Forest** | 10.2% | `█████████████░░` |
| **Kalman Trend** | 10.1% | `█████████████░░` |
| **Psych Sweep** | 9.7% | `████████████░░░` |
| **News Sentiment** | 6.0% | `███████░░░░░░░░` |


---

## Weekly Sentiment Source Attribution & Optimization

| News/Social Source | Sample Count | Correlation (PnL) | Active Weight |
| --- | --- | --- | --- |
| **cointelegraph** | 1 | +0.0000 | **1.0000** |
| **cryptobriefing** | 1 | +0.0000 | **1.0000** |
| **beincrypto** | 4 | +0.5985 | **1.5985** |
| **reddit** | 1 | +0.0000 | **1.0000** |
---


## Weekly Hyperparameter Backtest Optimization & Self-Improvement
Optimizations run over a window of **5000** historical price ticks.

### Optimized Strategy Parameters:
* **RSI Reversion Strategy**: Oversold Threshold = `35.0`, Overbought Threshold = `65.0` (Backtest PnL: `€458798.6290`)
* **Kalman Filter Trend Strategy**: Trigger Filter Threshold = `0.0010` / `0.10%` (Backtest PnL: `€-999999.0000`)
* **Volatility ATR Risk Strategy**: Take Profit Multiplier = `3.5x ATR`, Stop Loss Multiplier = `1.0x ATR` (Backtest PnL: `€5582.5689`)

### Policy Gradient Neural Network Evaluation:
Evaluating neural network weights update records...
* Recent 20 Trades Win Rate: **10.0%** | Average Trade PnL: **€-0.02**
* Policy Gradient NN backpropagation gradient steps verified: **Stable**.

### 💡 AI Parameter Optimizer Evaluation:
[OpenClawBridge ERROR] Failed after 3 retries for Parameter Optimizer Agent
---

## 📈 Detailed Strategy Attribution
This table highlights how individual strategies contributed to the trades opened during this period. A strategy is considered "aligned" if its voting signal matches the entry direction of the executed trade.

| Strategy Component | Aligned Trades | Win Rate When Aligned | Net Strategy PnL |
| :--- | :--- | :--- | :--- |
| EMA Crossover | 8 | 12.5% | €-0.21 |
| RSI Reversion | 0 | - | €+0.00 |
| BB Breakout | 1 | 0.0% | €-0.01 |
| ML Random Forest | 4 | 25.0% | €-0.05 |
| Kalman Trend | 5 | 20.0% | €-0.15 |
| Psych Sweep | 0 | - | €+0.00 |
| News Sentiment | 1 | 0.0% | €-0.02 |


---

## 🔍 Trade Diagnostics & Extremes

* 🟢 **Best Execution:** **DOT-USD** (BUY) - Exit PnL: **€0.01** (+0.15%) via *Stop Loss*
* 🔴 **Worst Drawdown:** **DOT-USD** (BUY) - Exit PnL: **€-0.04** (-0.93%) via *Stop Loss*


### Cumulative Balance Progression
| Trade # | Ticker | Side | Net PnL | Portfolio Balance |
| --- | --- | --- | --- | --- |
| Start | - | - | - | €6.04 |
| 1 | DOGE-USD | BUY | €-0.01 | €6.02 |
| 2 | ADA-USD | BUY | €-0.02 | €6.01 |
| 3 | ETH-USD | SELL | €-0.02 | €5.99 |
| 4 | ADA-USD | SELL | €-0.04 | €5.95 |
| 5 | DOGE-USD | SELL | €-0.04 | €5.91 |
| 6 | DOT-USD | BUY | €+0.01 | €5.92 |
| 7 | ETH-USD | SELL | €-0.03 | €5.88 |
| 8 | DOT-USD | BUY | €-0.04 | €5.84 |
| 9 | BTC-USD | SELL | €-0.00 | €5.84 |
| 10 | LINK-USD | BUY | €-0.04 | €5.80 |


---

## 💡 System Insights & Quantitative Summary

1. **Regime Switching Adaptability:** The system uses Ornstein-Uhlenbeck process parameters to distinguish between trending and mean-reverting states. Under mean-reverting regimes, the neural network boosts weights for the **RSI Reversion**, **BB Breakout**, and **Psych Sweep** components, while suppressing trend-following metrics.
2. **Online Policy Gradient Optimization:** After each trade closes, the neural network runs a policy gradient backward pass using trade PnL as the reward. Successful trades strengthen the neural pathways of the voting strategies, while losing trades penalize their weights.
3. **Volatility-Adjusted Risk Sizing:** Take-profit and stop-loss boundaries are automatically computed using Average True Range (ATR) multiples. Sizing is governed by the Kelly Criterion (scaled by a fraction based on the risk profile), preventing catastrophic risk exposure.

---

## 🗺️ Quantitative Roadmap & Operational Plan
To optimize execution safety and target higher capital return frequencies, we are implementing a structured phased software roadmap:
1. **Diversified Multi-Asset Support (Active)**: We have transitioned the core loop to trade `ETH-EUR`, `SOL-EUR`, `BTC-EUR`, `DOGE-EUR`, and `XRP-EUR` concurrently under a single portfolio account.
2. **Limit Order Queue Simulation (Next Phase)**: To prevent execution slippage in live trading, we are implementing maker/taker transaction fee modelling and limit order fills based on tick high/low crossings.
3. **Daily Risk Safeguards & Circuit Breakers (Next Phase)**: Adding daily maximum drawdown boundaries (5% of daily start balance) that will automatically freeze the execution engines if breached, protecting the portfolio balance.

---
*Report generated automatically by the NexusTrader Blog Agent.*
