# Weekly Performance Log: NexusTrader Algorithmic Operations
**Reporting Period:** July 12, 2026 to July 19, 2026  
**System Status:** ACTIVE 🟢  
> [!IMPORTANT]
> **Operational Status:** `PAPER TRADING (LIVE SIMULATION)`  
> The system is running simulations on live market feed ticks. Trades are executed using virtual balances (paper trading) with zero capital risk.


Welcome to the weekly performance report of **NexusTrader**, a self-learning quantitative trading bot driven by an ensemble of technical strategies and optimized in real-time by a Policy Gradient Neural Network.

Below is an extensive breakdown of the system's performance, resource allocations, neural network adaptations, and trading diagnostics.

---

## 📊 Executive Portfolio Summary

| Metric | Value |
| :--- | :--- |
| **Current Account Equity** | **€1789.15** |
| **Starting Balance (Week Start)** | €1790.58 |
| **Net PnL (Euros)** | **€-1.43** |
| **Weekly Return (%)** | **-0.08%** |
| **Risk Profile Configuration** | `AGGRESSIVE` |
| **Active Trade Count** | 42 |
| **Overall System Win Rate** | **31.0%** |
| **Profit Factor** | **0.33** |

---

## 💼 Portfolio Asset Performance Breakdown
Performance metrics segmented by individual portfolio asset ticker:

| Asset Ticker | Trades Executed | Win Rate | Net Asset PnL |
| :--- | :--- | :--- | :--- |
| BTC-EUR | 11 | 36.4% | €-0.59 |
| DOGE-EUR | 5 | 60.0% | €-0.17 |
| ETH-EUR | 5 | 20.0% | €-0.27 |
| SOL-EUR | 10 | 30.0% | €-0.26 |
| XRP-EUR | 11 | 18.2% | €-0.13 |


---

## 🧠 Neural Policy Network Allocations
The Policy Gradient Neural Network dynamically distributes weights among individual strategies on each tick. It monitors indicators (OU market regime parameters, RSI, Bollinger position, ATR volatility, and win rate trend) to shift allocations toward strategies that perform best in current conditions.

Current baseline weights computed by the neural network:

| Strategy | Allocation Weight | Visual Distribution |
| :--- | :--- | :--- |
| **EMA Crossover** | 7.9% | `██████░░░░░░░░░` |
| **RSI Reversion** | 19.7% | `███████████████` |
| **BB Breakout** | 16.7% | `█████████████░░` |
| **ML Random Forest** | 13.1% | `██████████░░░░░` |
| **Kalman Trend** | 11.9% | `█████████░░░░░░` |
| **Psych Sweep** | 18.3% | `██████████████░` |
| **News Sentiment** | 12.2% | `█████████░░░░░░` |


---

## Weekly Sentiment Source Attribution & Optimization

| News/Social Source | Sample Count | Correlation (PnL) | Active Weight |
| --- | --- | --- | --- |
| **cointelegraph** | 13 | -0.2284 | **0.7716** |
| **cryptobriefing** | 8 | -0.2567 | **0.7433** |
| **beincrypto** | 15 | +0.1922 | **1.1922** |
| **reddit** | 9 | +0.1539 | **1.1539** |
---


## Weekly Hyperparameter Backtest Optimization & Self-Improvement
Optimizations run over a window of **4095** historical price ticks.

### Optimized Strategy Parameters:
* **RSI Reversion Strategy**: Oversold Threshold = `40.0`, Overbought Threshold = `60.0` (Backtest PnL: `€2066852.9937`)
* **Kalman Filter Trend Strategy**: Trigger Filter Threshold = `0.0010` / `0.10%` (Backtest PnL: `€-999999.0000`)
* **Volatility ATR Risk Strategy**: Take Profit Multiplier = `3.5x ATR`, Stop Loss Multiplier = `1.0x ATR` (Backtest PnL: `€8413.6964`)

### Policy Gradient Neural Network Evaluation:
Evaluating neural network weights update records...
* Recent 20 Trades Win Rate: **20.0%** | Average Trade PnL: **€-0.05**
* Policy Gradient NN backpropagation gradient steps verified: **Stable**.

### 💡 AI Recommendations Status:
*AI recommendations disabled or API key not configured in settings.*
---

## 📈 Detailed Strategy Attribution
This table highlights how individual strategies contributed to the trades opened during this period. A strategy is considered "aligned" if its voting signal matches the entry direction of the executed trade.

| Strategy Component | Aligned Trades | Win Rate When Aligned | Net Strategy PnL |
| :--- | :--- | :--- | :--- |
| EMA Crossover | 36 | 33.3% | €-0.90 |
| RSI Reversion | 15 | 33.3% | €-0.58 |
| BB Breakout | 8 | 12.5% | €-0.24 |
| ML Random Forest | 7 | 14.3% | €-0.25 |
| Kalman Trend | 15 | 40.0% | €-0.82 |
| Psych Sweep | 0 | - | €+0.00 |
| News Sentiment | 7 | 14.3% | €-0.66 |


---

## 🔍 Trade Diagnostics & Extremes

* 🟢 **Best Execution:** **XRP-EUR** (BUY) - Exit PnL: **€0.20** (+0.69%) via *Take Profit*
* 🔴 **Worst Drawdown:** **BTC-EUR** (SELL) - Exit PnL: **€-0.36** (-0.19%) via *Stop Loss*


### Cumulative Balance Progression
| Trade # | Ticker | Side | Net PnL | Portfolio Balance |
| --- | --- | --- | --- | --- |
| Start | - | - | - | €1790.58 |
| 1 | ETH-EUR | BUY | €-0.02 | €1790.56 |
| 2 | ETH-EUR | BUY | €-0.02 | €1790.54 |
| 3 | DOGE-EUR | BUY | €-0.02 | €1790.53 |
| 4 | SOL-EUR | BUY | €-0.02 | €1790.51 |
| 5 | BTC-EUR | BUY | €-0.01 | €1790.50 |
| 6 | ETH-EUR | BUY | €-0.01 | €1790.49 |
| 7 | SOL-EUR | BUY | €-0.02 | €1790.48 |
| 8 | BTC-EUR | BUY | €-0.01 | €1790.46 |
| 9 | DOGE-EUR | BUY | €+0.01 | €1790.47 |
| 10 | SOL-EUR | BUY | €+0.01 | €1790.48 |
| 11 | BTC-EUR | BUY | €+0.00 | €1790.49 |
| 12 | XRP-EUR | BUY | €-0.03 | €1790.46 |
| 13 | DOGE-EUR | BUY | €+0.02 | €1790.49 |
| 14 | ETH-EUR | BUY | €+0.02 | €1790.51 |
| 15 | XRP-EUR | BUY | €+0.02 | €1790.52 |
| 16 | SOL-EUR | BUY | €+0.01 | €1790.53 |
| 17 | SOL-EUR | SELL | €-0.05 | €1790.49 |
| 18 | DOGE-EUR | BUY | €+0.03 | €1790.52 |
| 19 | SOL-EUR | SELL | €+0.20 | €1790.72 |
| 20 | ETH-EUR | BUY | €-0.25 | €1790.47 |
| 21 | DOGE-EUR | BUY | €-0.22 | €1790.25 |
| 22 | XRP-EUR | BUY | €-0.03 | €1790.22 |
| 23 | XRP-EUR | BUY | €-0.03 | €1790.19 |
| 24 | BTC-EUR | BUY | €-0.20 | €1789.99 |
| 25 | XRP-EUR | BUY | €-0.01 | €1789.98 |
| 26 | XRP-EUR | SELL | €-0.03 | €1789.94 |
| 27 | SOL-EUR | BUY | €-0.08 | €1789.86 |
| 28 | BTC-EUR | BUY | €+0.02 | €1789.88 |
| 29 | BTC-EUR | BUY | €+0.08 | €1789.96 |
| 30 | XRP-EUR | BUY | €+0.20 | €1790.16 |
| 31 | BTC-EUR | BUY | €+0.08 | €1790.25 |
| 32 | XRP-EUR | BUY | €-0.10 | €1790.15 |
| 33 | BTC-EUR | BUY | €-0.12 | €1790.03 |
| 34 | SOL-EUR | SELL | €-0.12 | €1789.91 |
| 35 | BTC-EUR | SELL | €-0.05 | €1789.85 |
| 36 | XRP-EUR | SELL | €-0.07 | €1789.79 |
| 37 | BTC-EUR | BUY | €-0.03 | €1789.76 |
| 38 | XRP-EUR | BUY | €-0.03 | €1789.73 |
| 39 | SOL-EUR | SELL | €-0.17 | €1789.57 |
| 40 | XRP-EUR | SELL | €-0.02 | €1789.55 |
| 41 | SOL-EUR | BUY | €-0.04 | €1789.51 |
| 42 | BTC-EUR | SELL | €-0.36 | €1789.15 |


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
