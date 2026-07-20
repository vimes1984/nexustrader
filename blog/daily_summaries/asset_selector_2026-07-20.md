# NexusTrader Asset Selector — Biweekly Report
**Date:** 2026-07-20 21:13 UTC
**Source:** Kraken USD Pairs / SQLite DB

---

## Current Active Assets (9 total — at cap)

| Ticker | 24h Vol (USD) | Price | Status |
|--------|---------------|-------|--------|
| BTC-USD | $134.5M | $65,292 | ✅ Active (mandatory) |
| ETH-USD | $51.5M | $1,905 | ✅ Active (mandatory) |
| SOL-USD | $21.6M | $77.91 | ✅ Active |
| XRP-USD | $10.2M | $1.12 | ✅ Active |
| SUI-USD | $7.0M | $0.77 | ✅ Active |
| ADA-USD | $6.9M | $0.17 | ✅ Active |
| DOGE-USD | $5.6M | $0.07 | ✅ Active |
| LTC-USD | $2.9M | $47.43 | ✅ Active |
| LINK-USD | $1.8M | $8.58 | ✅ Active |

**Inactive in DB:** AVAX-USD ($1.3M), DOT-USD ($648K — below $1M threshold)

All 9 active tickers clear the $1M minimum daily volume threshold. No zero-volume or delisted tickers detected.

---

## Kraken USD Pairs ≥ $1M (not currently active)

| Pair | 24h Vol (USD) | Sector / Notes |
|------|---------------|----------------|
| ZEC/USD | $7.8M | Privacy coin (low BTC/ETH correlation) |
| HYPE/USD | $5.6M | Hyperliquid — perps DEX / DeFi |
| NIGHT/USD | $4.8M | Newer listing |
| PUMP/USD | $2.8M | Meme |
| XLM/USD | $2.2M | Stellar — payments (correlated w/ XRP) |
| XMR/USD | $2.1M | Monero — privacy (low BTC/ETH correlation) |
| ESPORTS/USD | $2.4M | Gaming niche |
| NEAR/USD | $1.9M | L1 (correlated w/ existing L1s) |
| TAO/USD | $1.4M | Bittensor — AI (low correlation) |
| PEPE/USD | $1.3M | Meme |
| AVAX/USD | $1.3M | L1 (was inactive, borderline vol) |
| TRX/USD | $996K | Below threshold |
| UNI/USD | $866K | Below threshold |
| DOT/USD | $648K | Below threshold |

---

## Diversification Analysis

Current portfolio breakdown:
- **L1s (5):** BTC, ETH, ADA, SOL, SUI — heavy concentration
- **Payments/Settlement (2):** XRP, LTC
- **Oracle (1):** LINK
- **Meme (1):** DOGE
- **Missing sectors:** Privacy, AI, DeFi perps

**Correlation risk:** ADA, SOL, and SUI are all smart-contract L1s that tend to move together. Swapping one for a non-correlated asset would improve the risk profile.

---

## Recommendations

**No changes needed at this time.** Reasoning:

1. **All 9 active assets exceed the $1M threshold** — no forced removals
2. **Portfolio is at max capacity (9)** — any addition requires a swap
3. **Best swap candidates:** ZEC ($7.8M, privacy) or TAO ($1.4M, AI) would diversify best, but neither presents a compelling enough edge to justify swapping a healthy current holding
4. **Conservative stance:** The current set is performing. Swapping introduces execution risk and retraining overhead for the allocator
5. **Watchlist** for next cycle (2026-08-03): ZEC/USD (privacy), TAO/USD (AI), and XMR/USD (privacy) — if any of these grow volume or if a current asset drops below $1M

**Decision:** ⏸️ Hold current portfolio. No DB changes. No bot restart needed.

---

## Next Review
Scheduled: 2026-08-03
