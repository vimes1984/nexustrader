# Weekly Performance Log: NexusTrader Algorithmic Operations
**Reporting Period:** July 09, 2026 to July 16, 2026  
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
| **Current Account Equity** | **€99.96** |
| **Starting Balance (Week Start)** | €80.48 |
| **Net PnL (Euros)** | **€+19.48** |
| **Weekly Return (%)** | **+24.21%** |
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
| **EMA Crossover** | 16.7% | `███████████████` |
| **RSI Reversion** | 16.7% | `███████████████` |
| **BB Breakout** | 16.7% | `███████████████` |
| **ML Random Forest** | 16.7% | `███████████████` |
| **Kalman Trend** | 16.7% | `███████████████` |
| **Psych Sweep** | 16.7% | `███████████████` |


---

## 📈 Detailed Strategy Attribution
This table highlights how individual strategies contributed to the trades opened during this period. A strategy is considered "aligned" if its voting signal matches the entry direction of the executed trade.

| Strategy Component | Aligned Trades | Win Rate When Aligned | Net Strategy PnL |
| :--- | :--- | :--- | :--- |
| EMA Crossover | 9 | 77.8% | €+21.86 |
| RSI Reversion | 3 | 33.3% | €-1.47 |
| BB Breakout | 5 | 40.0% | €+0.22 |
| ML Random Forest | 6 | 66.7% | €+6.76 |
| Kalman Trend | 6 | 83.3% | €+15.36 |
| Psych Sweep | 4 | 25.0% | €-2.18 |


---

## 🔍 Trade Diagnostics & Extremes

* 🟢 **Best Execution:** **SOL-EUR** (SELL) - Exit PnL: **€7.32** (+4.03%) via *Take Profit*
* 🔴 **Worst Drawdown:** **SOL-EUR** (BUY) - Exit PnL: **€-3.90** (-2.02%) via *Stop Loss*


### Cumulative Balance Progression
| Trade # | Ticker | Side | Net PnL | Portfolio Balance |
| --- | --- | --- | --- | --- |
| Start | - | - | - | €80.48 |
| 1 | BTC-EUR | SELL | €-1.50 | €78.98 |
| 2 | ETH-EUR | BUY | €-2.38 | €76.60 |
| 3 | SOL-EUR | SELL | €+7.32 | €83.92 |
| 4 | XRP-EUR | BUY | €+2.40 | €86.32 |
| 5 | BTC-EUR | BUY | €+3.55 | €89.87 |
| 6 | ETH-EUR | BUY | €+4.81 | €94.68 |
| 7 | SOL-EUR | BUY | €-3.90 | €90.78 |
| 8 | DOGE-EUR | BUY | €+5.60 | €96.38 |
| 9 | ETH-EUR | SELL | €+2.97 | €99.35 |
| 10 | BTC-EUR | BUY | €+0.61 | €99.96 |


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
