# 🤝 NexusTrader Developer Handoff & Project Guide

Welcome! This handoff document provides a systems-engineered overview of **NexusTrader** (our quantitative algorithmic crypto-trading bot) for developers and AI agents (such as `openclaw`) to pick up the codebase seamlessly.

---

## 1. Project Overview & Environment
* **Platform**: Event-driven crypto algorithmic trading daemon with a FastAPI backend and a responsive Vanilla HTML/CSS/JS frontend dashboard.
* **Production Host**: Deployed in a Proxmox LXC container (`192.168.0.144`) running under a systemd daemon (`nexustrader.service`).
* **Starting Capital setting**: SQLite baseline balance persists in `settings` to avoid UI placeholder flashes.
* **Kraken Balances**: CAD, EUR, GBP, AUD, JPY are synced and converted dynamically using USD price tickers (EUR falls back to `1.12 USD` conversion if yfinance tickers are offline).

---

## 2. Core Systems Architecture & Layout

* **`main.py`**: The central backend server process. Runs FastAPI endpoints, controls ingestion loops, handles shadow/paper/live execution engine states, and serves the UI dashboard resources.
* **`dashboard/`**: Contains `/index.html`, `/index_v2.css`, and `/app_v2.js` providing the dashboard UI charts, logs console, optimizer controls, and setting inputs.
* **`quant_utils.py`**: Contains quantitative helper functions (Kalman trend filter, psychological sweep, Ornstein-Uhlenbeck solver) and handles LLM provider query routing (Gemini, OpenAI, Anthropic).
* **`backup_manager.py`**: Implements safe online hot-backups of the SQLite database (`VACUUM INTO`), configs, and logs. Compresses them into timestamped archives and applies a **7-day / 4-week / 12-month** pruning rotation.
* **`database.py`**: SQLite database initialization, column migrations, settings storage, and trade log storage.

---

## 3. Dynamic Daily Goal & Sizing Sizing Calculations
We transitioned the system from a hardcoded `$1,000 USD/day` target to a dynamic goal:
* **Storage**: Configured via the `daily_income_goal` settings parameter in the SQLite settings table.
* **Frontend Controller**: A dynamic Profit Target input card is situated at the top right of the **Long-Term Strategy** tab.
* **Adaptive Sizing Math**: The required capital sizing calculations dynamically adapt to the target using actual trade records:
  $$\text{Capital} = \frac{\text{Daily Goal}}{\text{Trades per Day} \times \text{Kelly Fraction} \times \text{Expectancy \%}}$$
* **Prompt Preprocessing**: `query_gemini_robust` dynamically intercepts and replaces all target goal numbers in agent prompts with the user's active setting (e.g. `$2,000 USD/day` if adjusted).

---

## 4. LLM Routing & The Antigravity Proxy (CRITICAL ⚠️)
The sandbox credentials for LLM queries utilize **Antigravity API Keys** (which start with the prefix `AQ.`).
* **Gemini Restriction**: Standard public Google Gemini API endpoints will reject these keys as invalid.
* **The Proxy**: We run `antigravity_proxy.py` on `127.0.0.1:8001`. This proxy wraps the local `google.antigravity` python package (which correctly parses the `AQ.` keys) and exposes a standard Gemini REST interface.
* **Routing Logic**: `query_gemini_robust` automatically performs a health check on `http://127.0.0.1:8001/health`. If online, it routes all Gemini requests locally through the proxy.
* **Local Run Command**: If testing agent self-development or LLM queries locally, execute the proxy first:
  ```bash
  python3 antigravity_proxy.py &
  ```

---

## 5. Deployment, Backups, & Operations CLI

* **Run All Tests**: We have **71 passing unit tests** covering all mathematical, database, and API layers:
  ```bash
  python3 -m unittest discover -s tests/
  ```
* **Deploy Code**: Trigger the deployment script, which runs unit tests locally, syncs the code files, restarts the Proxmox systemd service, and schedules/configures the daily backup cron:
  ```bash
  ./deploy.sh
  ```
* **Cron backup Schedule**: Daily backups run automatically on the container at **3:00 AM** via a system crontab entry calling `backup_manager.py`.
* **Manual backup Trigger**:
  ```bash
  python3 backup_manager.py backup
  ```
* **Restore Backup**:
  ```bash
  python3 backup_manager.py restore <backup_archive_path.tar.gz>
  ```

---

## 6. Next Steps for Optimization
* **Expectancy Scaling**: Mined trades currently show a negative expectancy of `-0.03%` due to commission/slippage drag. Optimize the ATR multipliers and neural gating weights to turn expectancy positive.
* **Shadow vs Live Validation**: Validate parameters using walk-forward shadow mode testing before shifting live capital from Paper simulation.
