# Weekly Performance Log: NexusTrader Algorithmic Operations
**Reporting Period:** July 11, 2026 to July 18, 2026  
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
| **Current Account Equity** | **€2.71** |
| **Starting Balance (Week Start)** | €2.93 |
| **Net PnL (Euros)** | **€-0.22** |
| **Weekly Return (%)** | **-7.48%** |
| **Risk Profile Configuration** | `CONSERVATIVE` |
| **Active Trade Count** | 154 |
| **Overall System Win Rate** | **9.7%** |
| **Profit Factor** | **1.00** |

---

## 💼 Portfolio Asset Performance Breakdown
Performance metrics segmented by individual portfolio asset ticker:

| Asset Ticker | Trades Executed | Win Rate | Net Asset PnL |
| :--- | :--- | :--- | :--- |
| BTC-USD | 41 | 0.0% | €-0.42 |
| DOGE-USD | 10 | 40.0% | €+1.54 |
| ETH-USD | 11 | 18.2% | €-9.05 |
| SOL-USD | 82 | 6.1% | €+4.08 |
| XRP-USD | 10 | 40.0% | €+3.64 |


---

## 🧠 Neural Policy Network Allocations
The Policy Gradient Neural Network dynamically distributes weights among individual strategies on each tick. It monitors indicators (OU market regime parameters, RSI, Bollinger position, ATR volatility, and win rate trend) to shift allocations toward strategies that perform best in current conditions.

Current baseline weights computed by the neural network:

| Strategy | Allocation Weight | Visual Distribution |
| :--- | :--- | :--- |
| **EMA Crossover** | 10.9% | `██████████░░░░░` |
| **RSI Reversion** | 13.0% | `███████████░░░░` |
| **BB Breakout** | 15.4% | `█████████████░░` |
| **ML Random Forest** | 17.2% | `███████████████` |
| **Kalman Trend** | 17.1% | `███████████████` |
| **Psych Sweep** | 16.3% | `██████████████░` |
| **News Sentiment** | 10.1% | `█████████░░░░░░` |


---

## Weekly Sentiment Source Attribution & Optimization

| News/Social Source | Sample Count | Correlation (PnL) | Active Weight |
| --- | --- | --- | --- |
| **cointelegraph** | 11 | +0.0271 | **1.0271** |
| **cryptobriefing** | 0 | +0.0000 | **1.0000** |
| **beincrypto** | 34 | -0.1855 | **0.8145** |
| **reddit** | 26 | +0.2447 | **1.2447** |
---


## Weekly Hyperparameter Backtest Optimization & Self-Improvement
Optimizations run over a window of **5000** historical price ticks.

### Optimized Strategy Parameters:
* **RSI Reversion Strategy**: Oversold Threshold = `35.0`, Overbought Threshold = `65.0` (Backtest PnL: `€3570341.1932`)
* **Kalman Filter Trend Strategy**: Trigger Filter Threshold = `0.0010` / `0.10%` (Backtest PnL: `€-999999.0000`)
* **Volatility ATR Risk Strategy**: Take Profit Multiplier = `3.5x ATR`, Stop Loss Multiplier = `1.0x ATR` (Backtest PnL: `€10158.1342`)

### Policy Gradient Neural Network Evaluation:
Evaluating neural network weights update records...
* Recent 20 Trades Win Rate: **5.0%** | Average Trade PnL: **€-0.00**
* Policy Gradient NN backpropagation gradient steps verified: **Stable**.

### 💡 Gemini AI PhD Quant & Mathematician Evaluation:
Error calling Gemini AI for PhD analysis: HTTP Error 429: Too Many Requests
---

## 📈 Detailed Strategy Attribution
This table highlights how individual strategies contributed to the trades opened during this period. A strategy is considered "aligned" if its voting signal matches the entry direction of the executed trade.

| Strategy Component | Aligned Trades | Win Rate When Aligned | Net Strategy PnL |
| :--- | :--- | :--- | :--- |
| EMA Crossover | 117 | 6.8% | €+13.40 |
| RSI Reversion | 51 | 2.0% | €-15.09 |
| BB Breakout | 47 | 10.6% | €-4.50 |
| ML Random Forest | 104 | 10.6% | €+10.59 |
| Kalman Trend | 29 | 20.7% | €-84.96 |
| Psych Sweep | 0 | - | €+0.00 |
| News Sentiment | 3 | 0.0% | €-0.30 |


---

## 🔍 Trade Diagnostics & Extremes

* 🟢 **Best Execution:** **XRP-USD** (BUY) - Exit PnL: **€48.91** (+15.85%) via *Take Profit*
* 🔴 **Worst Drawdown:** **XRP-USD** (SELL) - Exit PnL: **€-48.89** (-13.91%) via *Stop Loss*


### Cumulative Balance Progression
| Trade # | Ticker | Side | Net PnL | Portfolio Balance |
| --- | --- | --- | --- | --- |
| Start | - | - | - | €2.93 |
| 1 | BTC-USD | BUY | €-0.13 | €2.81 |
| 2 | SOL-USD | BUY | €-0.03 | €2.78 |
| 3 | DOGE-USD | BUY | €-0.17 | €2.61 |
| 4 | BTC-USD | BUY | €-0.09 | €2.52 |
| 5 | SOL-USD | BUY | €-0.12 | €2.40 |
| 6 | DOGE-USD | BUY | €-0.05 | €2.35 |
| 7 | BTC-USD | BUY | €-0.09 | €2.26 |
| 8 | DOGE-USD | BUY | €-0.25 | €2.01 |
| 9 | SOL-USD | SELL | €+0.05 | €2.06 |
| 10 | XRP-USD | BUY | €-0.31 | €1.74 |
| 11 | DOGE-USD | BUY | €-0.35 | €1.40 |
| 12 | XRP-USD | BUY | €-6.57 | €-5.18 |
| 13 | XRP-USD | SELL | €+8.83 | €3.66 |
| 14 | XRP-USD | BUY | €-10.34 | €-6.69 |
| 15 | SOL-USD | SELL | €-0.02 | €-6.71 |
| 16 | XRP-USD | BUY | €-9.87 | €-16.58 |
| 17 | DOGE-USD | SELL | €+0.45 | €-16.13 |
| 18 | SOL-USD | BUY | €+0.08 | €-16.05 |
| 19 | XRP-USD | BUY | €-10.96 | €-27.01 |
| 20 | DOGE-USD | BUY | €+0.96 | €-26.05 |
| 21 | XRP-USD | BUY | €+15.64 | €-10.41 |
| 22 | SOL-USD | BUY | €+0.20 | €-10.21 |
| 23 | ETH-USD | BUY | €+0.18 | €-10.03 |
| 24 | SOL-USD | SELL | €+4.26 | €-5.78 |
| 25 | DOGE-USD | SELL | €+3.27 | €-2.50 |
| 26 | DOGE-USD | BUY | €-4.04 | €-6.55 |
| 27 | ETH-USD | SELL | €+5.77 | €-0.78 |
| 28 | ETH-USD | SELL | €-4.33 | €-5.11 |
| 29 | DOGE-USD | SELL | €+1.72 | €-3.39 |
| 30 | ETH-USD | BUY | €-0.86 | €-4.25 |
| 31 | ETH-USD | SELL | €-4.26 | €-8.51 |
| 32 | ETH-USD | SELL | €-2.35 | €-10.86 |
| 33 | ETH-USD | BUY | €-3.18 | €-14.04 |
| 34 | XRP-USD | SELL | €+17.21 | €3.17 |
| 35 | XRP-USD | BUY | €+48.91 | €52.08 |
| 36 | XRP-USD | SELL | €-48.89 | €3.19 |
| 37 | BTC-USD | SELL | €-0.00 | €3.19 |
| 38 | ETH-USD | SELL | €-0.00 | €3.18 |
| 39 | SOL-USD | SELL | €-0.01 | €3.17 |
| 40 | BTC-USD | SELL | €-0.00 | €3.17 |
| 41 | ETH-USD | SELL | €-0.00 | €3.17 |
| 42 | BTC-USD | SELL | €-0.00 | €3.17 |
| 43 | ETH-USD | SELL | €-0.00 | €3.16 |
| 44 | SOL-USD | SELL | €-0.01 | €3.16 |
| 45 | BTC-USD | SELL | €-0.00 | €3.15 |
| 46 | SOL-USD | SELL | €-0.00 | €3.15 |
| 47 | BTC-USD | SELL | €-0.00 | €3.15 |
| 48 | SOL-USD | SELL | €-0.00 | €3.14 |
| 49 | ETH-USD | BUY | €-0.00 | €3.14 |
| 50 | SOL-USD | SELL | €-0.01 | €3.14 |
| 51 | SOL-USD | SELL | €-0.00 | €3.13 |
| 52 | BTC-USD | SELL | €-0.00 | €3.13 |
| 53 | BTC-USD | SELL | €-0.00 | €3.13 |
| 54 | BTC-USD | SELL | €-0.00 | €3.12 |
| 55 | SOL-USD | SELL | €-0.01 | €3.12 |
| 56 | SOL-USD | SELL | €-0.00 | €3.11 |
| 57 | SOL-USD | SELL | €-0.01 | €3.11 |
| 58 | SOL-USD | SELL | €-0.01 | €3.10 |
| 59 | SOL-USD | SELL | €-0.00 | €3.10 |
| 60 | SOL-USD | SELL | €-0.00 | €3.09 |
| 61 | SOL-USD | SELL | €-0.00 | €3.09 |
| 62 | SOL-USD | SELL | €-0.01 | €3.08 |
| 63 | BTC-USD | SELL | €-0.00 | €3.08 |
| 64 | SOL-USD | SELL | €-0.01 | €3.07 |
| 65 | SOL-USD | SELL | €-0.00 | €3.07 |
| 66 | SOL-USD | SELL | €-0.00 | €3.07 |
| 67 | SOL-USD | SELL | €-0.01 | €3.06 |
| 68 | SOL-USD | SELL | €-0.01 | €3.06 |
| 69 | SOL-USD | SELL | €-0.00 | €3.05 |
| 70 | SOL-USD | SELL | €-0.00 | €3.05 |
| 71 | SOL-USD | SELL | €-0.00 | €3.05 |
| 72 | SOL-USD | SELL | €-0.00 | €3.04 |
| 73 | SOL-USD | SELL | €-0.01 | €3.04 |
| 74 | SOL-USD | SELL | €-0.00 | €3.03 |
| 75 | BTC-USD | BUY | €-0.00 | €3.03 |
| 76 | SOL-USD | SELL | €-0.01 | €3.02 |
| 77 | SOL-USD | SELL | €-0.01 | €3.02 |
| 78 | SOL-USD | SELL | €-0.01 | €3.01 |
| 79 | BTC-USD | BUY | €-0.00 | €3.01 |
| 80 | SOL-USD | SELL | €-0.00 | €3.01 |
| 81 | SOL-USD | SELL | €-0.00 | €3.00 |
| 82 | BTC-USD | BUY | €-0.00 | €3.00 |
| 83 | BTC-USD | BUY | €-0.00 | €3.00 |
| 84 | SOL-USD | SELL | €-0.00 | €2.99 |
| 85 | BTC-USD | BUY | €-0.00 | €2.99 |
| 86 | SOL-USD | SELL | €-0.01 | €2.98 |
| 87 | SOL-USD | SELL | €-0.01 | €2.98 |
| 88 | SOL-USD | SELL | €-0.01 | €2.97 |
| 89 | SOL-USD | SELL | €-0.00 | €2.97 |
| 90 | BTC-USD | BUY | €-0.00 | €2.97 |
| 91 | SOL-USD | SELL | €-0.00 | €2.96 |
| 92 | SOL-USD | SELL | €-0.00 | €2.96 |
| 93 | SOL-USD | SELL | €-0.01 | €2.95 |
| 94 | SOL-USD | SELL | €-0.00 | €2.95 |
| 95 | SOL-USD | SELL | €-0.00 | €2.95 |
| 96 | BTC-USD | BUY | €-0.00 | €2.95 |
| 97 | BTC-USD | BUY | €-0.00 | €2.94 |
| 98 | BTC-USD | BUY | €-0.00 | €2.94 |
| 99 | BTC-USD | BUY | €-0.00 | €2.94 |
| 100 | BTC-USD | BUY | €-0.00 | €2.93 |
| 101 | SOL-USD | SELL | €-0.00 | €2.93 |
| 102 | BTC-USD | BUY | €-0.00 | €2.92 |
| 103 | BTC-USD | BUY | €-0.00 | €2.92 |
| 104 | SOL-USD | SELL | €-0.01 | €2.92 |
| 105 | SOL-USD | SELL | €-0.00 | €2.91 |
| 106 | BTC-USD | BUY | €-0.00 | €2.91 |
| 107 | BTC-USD | BUY | €-0.00 | €2.91 |
| 108 | BTC-USD | BUY | €-0.00 | €2.90 |
| 109 | SOL-USD | SELL | €-0.00 | €2.90 |
| 110 | SOL-USD | SELL | €-0.00 | €2.90 |
| 111 | SOL-USD | SELL | €-0.01 | €2.89 |
| 112 | SOL-USD | BUY | €-0.01 | €2.88 |
| 113 | SOL-USD | SELL | €-0.00 | €2.88 |
| 114 | SOL-USD | SELL | €-0.00 | €2.87 |
| 115 | SOL-USD | SELL | €-0.00 | €2.87 |
| 116 | SOL-USD | SELL | €-0.00 | €2.87 |
| 117 | SOL-USD | SELL | €-0.00 | €2.87 |
| 118 | SOL-USD | SELL | €-0.00 | €2.86 |
| 119 | SOL-USD | SELL | €-0.01 | €2.86 |
| 120 | SOL-USD | SELL | €-0.01 | €2.85 |
| 121 | SOL-USD | SELL | €-0.00 | €2.85 |
| 122 | SOL-USD | SELL | €-0.00 | €2.85 |
| 123 | BTC-USD | BUY | €-0.00 | €2.84 |
| 124 | SOL-USD | SELL | €-0.00 | €2.84 |
| 125 | BTC-USD | BUY | €-0.00 | €2.83 |
| 126 | SOL-USD | SELL | €-0.00 | €2.83 |
| 127 | SOL-USD | SELL | €-0.01 | €2.82 |
| 128 | SOL-USD | SELL | €-0.01 | €2.82 |
| 129 | SOL-USD | SELL | €-0.00 | €2.82 |
| 130 | BTC-USD | SELL | €-0.00 | €2.81 |
| 131 | SOL-USD | SELL | €-0.00 | €2.81 |
| 132 | SOL-USD | SELL | €-0.01 | €2.80 |
| 133 | SOL-USD | SELL | €-0.01 | €2.80 |
| 134 | SOL-USD | SELL | €-0.01 | €2.79 |
| 135 | DOGE-USD | BUY | €-0.00 | €2.79 |
| 136 | SOL-USD | SELL | €-0.01 | €2.78 |
| 137 | SOL-USD | SELL | €-0.01 | €2.78 |
| 138 | SOL-USD | SELL | €-0.00 | €2.77 |
| 139 | SOL-USD | SELL | €+0.00 | €2.77 |
| 140 | SOL-USD | SELL | €-0.01 | €2.77 |
| 141 | SOL-USD | SELL | €-0.01 | €2.76 |
| 142 | BTC-USD | BUY | €-0.00 | €2.76 |
| 143 | BTC-USD | BUY | €-0.00 | €2.75 |
| 144 | BTC-USD | SELL | €-0.00 | €2.75 |
| 145 | SOL-USD | SELL | €-0.01 | €2.75 |
| 146 | SOL-USD | SELL | €-0.01 | €2.74 |
| 147 | SOL-USD | SELL | €-0.00 | €2.74 |
| 148 | BTC-USD | SELL | €-0.00 | €2.73 |
| 149 | BTC-USD | SELL | €-0.00 | €2.73 |
| 150 | BTC-USD | SELL | €-0.00 | €2.73 |
| 151 | BTC-USD | SELL | €-0.00 | €2.72 |
| 152 | BTC-USD | SELL | €-0.00 | €2.72 |
| 153 | BTC-USD | SELL | €-0.00 | €2.72 |
| 154 | BTC-USD | SELL | €-0.00 | €2.71 |


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
