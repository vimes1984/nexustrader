# DevSwarm MathDataSignals Batch — Complete

## Summary
26 iterations across 5+ target files, fixing 19 data quality, feature engineering, and statistical bugs in the NexusTrader repo.

## Commits (Chronological)

### Phase 1: Feature Engineering & OHLCV Math
| Iter | File | Fix |
|------|------|-----|
| 1 | historical_pipeline.py | ATR prev_c offset: `price_history[-1]` diverged from `buf[j-1]` for oldest candle in the 14-period window |
| 9 | database.py | `load_weights_history` sort order: DESC default with ASC option |
| 14 | historical_pipeline.py | Alignment vs reward scaling mismatch: linear clip(10x) vs tanh(20x) — unified to both use tanh |
| 16 | data_ingestion.py | Gap-fill created only 1 candle per connectivity gap regardless of duration causing timestamp desync; now fills all missing candles |
| 19 | historical_pipeline.py | Dead `win_trend` feature: `closed_trades` never populated in SimulatedTrader, always returning 0.5; now tracks forward_returns in `_wins_buf` |
| 20 | historical_pipeline.py | RSI mismatch between training (SMA) and inference (Wilder's RMA); now uses Wilder's RMA with running averages |
| 22 | data_ingestion.py | Deprecated `fillna(method='ffill')` → modern `ffill()`; added final fallback values for ATR (1% of close) and stoch_k (50.0) |
| 25 | data_ingestion.py | NaN propagation for bb\_* indicators: expanding.fillna() of NaN-only window still returns NaN; added `fillna(0.0)` fallback; close-based fallback for ATR |

### Phase 2: Data Integrity & Database
| Iter | File | Fix |
|------|------|-----|
| 17 | database.py | OHLCV data corruption in `save_tick`: INSERT OR REPLACE silently overwrote high/low with subsequent values; now uses `ON CONFLICT DO UPDATE SET high=MAX(high,excluded.high), low=MIN(low,excluded.low), volume=volume+excluded.volume` |
| 24 | weekly_optimizer.py | DB connection leak: `conn.close()` in try block without finally; added `conn=None` init + finally clause |

### Phase 3: Sentiment Scoring
| Iter | File | Fix |
|------|------|-----|
| 3 | sentiment_analyzer.py | FinBERT label order: ProsusAI/finbert outputs [neg, neu, pos], code used [pos, neg, neu] |
| 4 | sentiment_analyzer.py | Blend threshold created discontinuity at confidence boundary; now continuous blend |
| 5 | sentiment_analyzer.py | Volume-weight with sqrt(article_count) aggregation |
| 18 | sentiment_analyzer.py | `.squeeze()` could flatten batch dim incorrectly; use `[0]` for first batch element |
| 21 | sentiment_analyzer.py | Clamp nn_confidence to [0,1] to prevent NaN/negative blend weights |

### Phase 4: Train/Test Leakage & Statistical Testing
| Iter | File | Fix |
|------|------|-----|
| 2 | historical_pipeline.py | Chronological train/val split with embargo period instead of random shuffle |
| 11 | probability_engine.py | Look-ahead bias: ALL history rows (including future) used to estimate win probabilities; restricted to first 60% as safe window |
| 26 | historical_pipeline.py | **Critical**: `OfflineTrainer._train_batch` passed int `trade_direction` (1/-1/0) instead of string "BUY"/"SELL" to `backward()`, causing `dir_val` to always evaluate as SELL — **all offline gradient signals were inverted** |

### Phase 5: Code Quality & Prompt Optimization
| Iter | File | Fix |
|------|------|-----|
| 6 | long_term_quant.py | Empty-string crash on settings, hoisted imports, trade data summary in prompt |
| 10 | long_term_quant.py | Guard empty json_block from `json.loads` crash |
| 13 | monthly_researcher.py | Hoisted import, summarized trade data in prompt |
| 15 | self_improvement_agent.py | Summarized trade data in prompts |

## Files Touched (by fix count)
| File | Fix Count |
|------|-----------|
| historical_pipeline.py | 6 |
| sentiment_analyzer.py | 5 |
| data_ingestion.py | 3 |
| database.py | 2 |
| long_term_quant.py | 2 |
| probability_engine.py | 1 |
| monthly_researcher.py | 1 |
| self_improvement_agent.py | 1 |
| weekly_optimizer.py | 1 |

## Impact Assessment
1. **Training signal corruption (iter 26)**: OfflineTrainer was training with inverted gradients — replacing int direction with string "BUY"/"SELL" fixes this
2. **OHLCV data integrity (iter 17)**: `INSERT OR REPLACE` could corrupt high/low for duplicate timestamps; `ON CONFLICT DO UPDATE` with MAX/MIN fixes
3. **Look-ahead bias (iter 11, 2)**: Win probability estimation and train/val split both had future-data leakage
4. **Feature inconsistency (iter 20, 14)**: RSI formula mismatch between training/inference and alignment/reward scale mismatch
5. **Model robustness (iter 3, 21, 25)**: Incorrect FinBERT label order, unclamped blend weights, NaN propagation
