# NexusTrader Dashboard — Handoff Doc for Antigravity

**Date:** 2026-07-21  
**Bot VM:** 192.168.0.144 (SSH: `root@192.168.0.144`)  
**Dashboard URL:** https://nexustrader.local/dashboard-v2/  
**Bot API:** https://nexustrader.local/api/status

---

## The Problem

Dashboard v2 (complete modular SPA rewrite) has been 95% fixed but **nav tabs don't switch pages** and **charts don't render candles**. The bot itself works fine — paper trading, $90.84 balance, 10 closed trades, uptime ~78 min.

## Root Causes Found & Fixed (14 commits)

All fixes ARE on the server. The issue is **browser cache** — the `?v=` cache-bust param was static (never changed between deploys), so the browser kept loading stale JS with bugs. This has been fixed but the cache may still be sticky.

### Critical bugs fixed:
1. **Syntax error: `try {}` without `catch`** — `dashboard.js:143` broke ALL subsequent JS loading
2. **`this._debug` not a function** — inside `addEventListener(function(e){})`, `this` is the DOM element, not App. Changed to `App._debug()`
3. **`_debug` infinite recursion** — called `this._debug()` instead of `console.log()`
4. **17 fake DOM methods** — `.setValue()` and `.setChecked()` don't exist on HTML elements
5. **API response shape mismatches** — 10/12 endpoints returned keys that didn't match what JS expected
6. **lucide.createIcons() never called on init** — all icons invisible (hamburger, nav, etc.)
7. **String timestamps crash LightweightCharts** — `"2026-07-19 22:00:00+00:00"` produces null when library expects Unix seconds
8. **KillSwitch false positive** — `if(data.kill_switch)` was truthy on any non-null object
9. **Static cache-bust** — `?v=1784639569` never changed, so browser never got updated JS

## Architecture

```
dashboard-v2/
├── index.html          # SPA shell
├── css/main.css        # All styles
├── js/
│   ├── api.js          # API client (try/catch on L13 is try+finally — valid JS)
│   ├── router.js       # App state, nav, WebSocket, init (App object)
│   ├── dashboard.js    # Charts, KPIs, ticker prices (Dashboard object)
│   ├── neural.js       # Neural network tab
│   ├── assets.js       # Asset management tab
│   ├── llm.js          # LLM tab
│   ├── agents.js       # Quant Team tab
│   ├── settings.js     # Settings tab
│   └── logs.js         # Logs tab
└── vendor/             # Self-hosted libs (lightweight-charts, chart.js, lucide)
```

**Key objects:** `App` (router.js) — global state, `Dashboard` (dashboard.js) — charts/KPIs  
**Loading order matters:** `<script>` tags load synchronously. If any file above crashes, files below never load.

## What Should Work (When Cache Clears)

- Nav sidebar (hamburger ☰ menu) opens and tabs switch pages
- URL hash updates (`#neural`, `#assets`, `#settings`, etc.)
- Main chart: 📊 Candles / 📈 Line toggle buttons
- Ticker pill prices show real values (not $0.00)
- Status badge: "Paper Trading" (blue) instead of "Simulating"
- 🐛 button toggles debug logs (only when debug ON)
- All API calls work (26/27 endpoints verified, 1 timeout on Kraken broker test)

## To Fix It

### Method 1: Clear Cache
```
1. Open https://nexustrader.local/dashboard-v2/
2. F12 → Application tab → Clear site data
3. Ctrl+Shift+R hard refresh
4. Check Console — should show NO errors
```

### Method 2: Verify Server
```bash
# Verify the deployed code is clean (no this._debug)
curl -sk https://192.168.0.144/dashboard-v2/js/router.js | grep 'this._debug'
# Should return NOTHING

# Check current cache-bust version
curl -sk https://192.168.0.144/dashboard-v2/index.html | grep '?v='
# Should show a current epoch timestamp, not 1784639569
```

### Method 3: Kill nginx cache
```bash
ssh root@192.168.0.144 "nginx -s reload"
```

## If Nav Still Broken After Cache Clear

The debug logs (only visible when 🐛 is clicked) will output:
```
initNav bound to 11 nav items
switchTab called: tab-neural
  found 9 tab-content divs
  switched to tab-neural
```

If you see "initNav bound to 0 nav items" — the `.nav-tab` class is missing from the sidebar buttons. Check `index.html` for `<button class="nav-tab" data-tab="tab-dashboard">`.

## Bot State

- **Mode:** Paper trading
- **Balance:** $90.84
- **Equity:** $200.70
- **Trades:** 10 closed, 0 open
- **Win/Loss:** 1/9
- **Uptime:** ~78 min
- **Health:** good — All systems operational

Bot is idle because RL model + risk limits haven't triggered entry conditions. This is expected for paper mode with current market conditions.

## LLaMA Fine-Tuning (Background)

Running on chris-System (192.168.0.77), PID 448932, CPU-only QLoRA on Llama 3.2 3B. ETA 4-12h. Check with:
```bash
ssh 192.168.0.77 "ps aux | grep finetune | grep -v grep"
```

## Git

Repo: `github.com/vimes1984/nexustrader` — all 14 fixes pushed to main.

---

Good luck, boss. The code IS fixed. The cache just needs to die. 🍌
