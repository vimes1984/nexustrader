# Changelog

All notable changes to NexusTrader will be documented in this file.

## [Unreleased]

### Added (2026-07-21)
- **LLM Management Tab**: Dashboard panel for LLaMA 3.2 3B integration
  - LLaMA status card (connected/model/tok_per_sec)
  - NN architecture selector (MLP/LSTM/Transformer radio buttons)
  - Sentiment/regime analysis triggers
  - LLM config editor (endpoint, interval, timeout, enable/disable)
  - NN test runner, training triggers
- **9 Backend API endpoints**: /api/llm/status, /test, /sentiment, /regime, /config,
  /api/nn/architecture, /api/nn/tests, /api/training/run
- **E2E Strategy Tests** (18 passing): test_e2e_strategy.py
- **Historical Training Pipeline**: historical_pipeline.py (DataFetcher, SimulatedTrader, OfflineTrainer)
- **Transformer Policy Network**: multi_head_attention.py + transformer_policy_net.py
- **LSTM Policy Network**: token_embedder.py + sequential_policy_net.py
- **Market Tokenizer**: tokenizer.py (32-token vocabulary)
- **LLaMA Client**: llm_client.py (3 roles: sentiment, regime, trade explanation)

### Fixed (2026-07-21)
- **WebSocket DISCONNECTED**: SUI-USD KeyError on every connect (yfinance delisted)
- **Dashboard frontend not served**: root/ vs dashboard/ directory mismatch
- **xhr() helper missing**: All Quant Team AJAX calls silently failing
- **Architecture tab**: Updated to reflect 9 tickers, 6 strategies, NN architectures, LLaMA flow
- **MIGRATION log spam**: Demoted from WARNING to DEBUG

### Removed (2026-07-20)
- SUI-USD ticker (yfinance "possibly delisted")
- 36 strategies purged (72→36→6 active)
- PPO agent and dependencies

## [1.0.0] - 2026-07-19
- Initial dashboard release
- Live Kraken trading (cash: ~$90)
- 6-strategy ensemble per ticker
- WebSocket real-time updates
- Neural training tab
- Quant Team agents (OpenClaw Gateway)
