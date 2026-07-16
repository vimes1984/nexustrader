# Weekly Performance Log: NexusTrader Algorithmic Operations
**Reporting Period:** July 10, 2026 to July 17, 2026  
**System Status:** ACTIVE 🟢  
> [!NOTE]
> **Operational Status:** `SAMPLE DATA (MOCK TEST DATA)`  
> This report was generated using synthetic trade history for demonstration and testing purposes. No assets were traded. No real money or live connection was active.


Welcome to the weekly performance report of **NexusTrader**, a self-learning quantitative trading bot driven by an ensemble of technical strategies and optimized in real-time by a Policy Gradient Neural Network.

Below is an extensive breakdown of the system's performance, resource allocations, neural network adaptations, and trading diagnostics.

---

## 📊 Executive Portfolio Summary

| Metric | Value |
| :--- | :--- |
| **Current Account Equity** | **€129.90** |
| **Starting Balance (Week Start)** | €110.42 |
| **Net PnL (Euros)** | **€+19.48** |
| **Weekly Return (%)** | **+17.64%** |
| **Risk Profile Configuration** | `AGGRESSIVE` |
| **Active Trade Count** | 10 |
| **Overall System Win Rate** | **70.0%** |
| **Profit Factor** | **3.50** |

---

## 💼 Portfolio Asset Performance Breakdown
Performance metrics segmented by individual portfolio asset ticker:

| Asset Ticker | Trades Executed | Win Rate | Net Asset PnL |
| :--- | :--- | :--- | :--- |
| BTC-EUR | 3 | 66.7% | €+2.66 |
| DOGE-EUR | 1 | 100.0% | €+5.60 |
| ETH-EUR | 3 | 66.7% | €+5.40 |
| SOL-EUR | 2 | 50.0% | €+3.42 |
| XRP-EUR | 1 | 100.0% | €+2.40 |


---

## 🧠 Neural Policy Network Allocations
The Policy Gradient Neural Network dynamically distributes weights among individual strategies on each tick. It monitors indicators (OU market regime parameters, RSI, Bollinger position, ATR volatility, and win rate trend) to shift allocations toward strategies that perform best in current conditions.

Current baseline weights computed by the neural network:

| Strategy | Allocation Weight | Visual Distribution |
| :--- | :--- | :--- |
| **EMA Crossover** | 14.3% | `███████████████` |
| **RSI Reversion** | 14.3% | `███████████████` |
| **BB Breakout** | 14.3% | `███████████████` |
| **ML Random Forest** | 14.3% | `███████████████` |
| **Kalman Trend** | 14.3% | `███████████████` |
| **Psych Sweep** | 14.3% | `███████████████` |
| **News Sentiment** | 14.3% | `███████████████` |


---

## Weekly Sentiment Source Attribution & Optimization

| News/Social Source | Sample Count | Correlation (PnL) | Active Weight |
| --- | --- | --- | --- |
| **cointelegraph** | 0 | +0.0000 | **1.0000** |
| **cryptobriefing** | 0 | +0.0000 | **1.0000** |
| **beincrypto** | 0 | +0.0000 | **1.0000** |
| **reddit** | 0 | +0.0000 | **1.0000** |
---


## Weekly Hyperparameter Backtest Optimization & Self-Improvement
Optimizations run over a window of **201** historical price ticks.

### Optimized Strategy Parameters:
* **RSI Reversion Strategy**: Oversold Threshold = `35.0`, Overbought Threshold = `65.0` (Backtest PnL: `€197.0212`)
* **Kalman Filter Trend Strategy**: Trigger Filter Threshold = `0.0010` / `0.10%` (Backtest PnL: `€-999999.0000`)

### Policy Gradient Neural Network Evaluation:
Evaluating neural network weights update records...
* Recent 20 Trades Win Rate: **75.0%** | Average Trade PnL: **€+2.66**
* Policy Gradient NN backpropagation gradient steps verified: **Stable**.

### 💡 AI Recommendations Status:
*Gemini AI recommendations disabled or API key not configured in settings.*
---

## 📈 Detailed Strategy Attribution
This table highlights how individual strategies contributed to the trades opened during this period. A strategy is considered "aligned" if its voting signal matches the entry direction of the executed trade.

| Strategy Component | Aligned Trades | Win Rate When Aligned | Net Strategy PnL |
| :--- | :--- | :--- | :--- |
| EMA Crossover | 0 | - | €+0.00 |
| RSI Reversion | 0 | - | €+0.00 |
| BB Breakout | 0 | - | €+0.00 |
| ML Random Forest | 0 | - | €+0.00 |
| Kalman Trend | 0 | - | €+0.00 |
| Psych Sweep | 0 | - | €+0.00 |
| News Sentiment | 0 | - | €+0.00 |


---

## 🔍 Trade Diagnostics & Extremes

* 🟢 **Best Execution:** **SOL-EUR** (SELL) - Exit PnL: **€7.32** (+4.03%) via *Take Profit*
* 🔴 **Worst Drawdown:** **SOL-EUR** (BUY) - Exit PnL: **€-3.90** (-2.02%) via *Stop Loss*


### Cumulative Balance Progression
| Trade # | Ticker | Side | Net PnL | Portfolio Balance |
| --- | --- | --- | --- | --- |
| Start | - | - | - | €110.42 |
| 1 | BTC-EUR | SELL | €-1.50 | €108.92 |
| 2 | ETH-EUR | BUY | €-2.38 | €106.54 |
| 3 | SOL-EUR | SELL | €+7.32 | €113.86 |
| 4 | XRP-EUR | BUY | €+2.40 | €116.26 |
| 5 | BTC-EUR | BUY | €+3.55 | €119.81 |
| 6 | ETH-EUR | BUY | €+4.81 | €124.62 |
| 7 | SOL-EUR | BUY | €-3.90 | €120.72 |
| 8 | DOGE-EUR | BUY | €+5.60 | €126.32 |
| 9 | ETH-EUR | SELL | €+2.97 | €129.29 |
| 10 | BTC-EUR | BUY | €+0.61 | €129.90 |


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
