#!/usr/bin/env python3
"""
COMPREHENSIVE KPI DASHBOARD FIX.

Backend:
1. /api/status: add today_pnl, today_pnl_pct, win_count, loss_count, 
   max_drawdown_pct, drawdown_limit, health_status, uptime_seconds

Frontend:
2. enhancer.js pollKpiPnL: rewrite to update ALL KPI cards
3. enhancer.js: add risk profile change handler as backup
4. enhancer.js: add uptime tracker
"""
import os, time, json, logging

# ============================================================
# 1. BACKEND: Enhance /api/status
# ============================================================
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

old_get_status = '''def get_status():
    current_prices = {}
    for t in orchestrator.tickers:
        if t in orchestrator.data_ingestions:
            current_prices[t] = orchestrator.data_ingestions[t].live_price or 0.0
            
    # Extract fiat breakdown from live_holdings
    ee = orchestrator.execution_engine
    fiat_breakdown = {}
    holdings = getattr(ee, "live_holdings", {})
    if holdings:
        for k, v in holdings.items():
            if k in ("USD", "ZUSD"):
                fiat_breakdown["USD"] = fiat_breakdown.get("USD", 0.0) + float(v)
            elif k in ("EUR", "ZEUR"):
                fiat_breakdown["EUR"] = fiat_breakdown.get("EUR", 0.0) + float(v)
            elif k in ("GBP", "ZGBP"):
                fiat_breakdown["GBP"] = fiat_breakdown.get("GBP", 0.0) + float(v)
    
    return {'''

new_get_status = '''def get_status():
    import datetime, os as _os
    current_prices = {}
    for t in orchestrator.tickers:
        if t in orchestrator.data_ingestions:
            current_prices[t] = orchestrator.data_ingestions[t].live_price or 0.0
    
    # Extract fiat breakdown from live_holdings
    ee = orchestrator.execution_engine
    fiat_breakdown = {}
    holdings = getattr(ee, "live_holdings", {})
    if holdings:
        for k, v in holdings.items():
            if k in ("USD", "ZUSD"):
                fiat_breakdown["USD"] = fiat_breakdown.get("USD", 0.0) + float(v)
            elif k in ("EUR", "ZEUR"):
                fiat_breakdown["EUR"] = fiat_breakdown.get("EUR", 0.0) + float(v)
            elif k in ("GBP", "ZGBP"):
                fiat_breakdown["GBP"] = fiat_breakdown.get("GBP", 0.0) + float(v)
    
    # Load trades for computed KPIs
    _db = __import__("database")
    _all_trades = _db.load_trades()
    
    # Today PnL
    _today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    _today_ts = _today_start.timestamp()
    _today_trades = [t for t in _all_trades if t.get("exit_time", 0) >= _today_ts]
    _today_pnl = sum(float(t.get("pnl", 0.0) or 0.0) for t in _today_trades)
    _today_pnl_pct = (_today_pnl / ee.balance * 100) if ee.balance > 0 else 0.0
    
    # Win/Loss
    _win_count = sum(1 for t in _all_trades if float(t.get("pnl", 0) or 0) > 0)
    _loss_count = sum(1 for t in _all_trades if float(t.get("pnl", 0) or 0) < 0)
    
    # Max drawdown from trade history
    _peak = ee.initial_balance
    _max_dd = 0.0
    _running = ee.initial_balance
    for t in sorted(_all_trades, key=lambda x: x.get("exit_time", 0)):
        _running += float(t.get("pnl", 0.0) or 0.0)
        if _running > _peak:
            _peak = _running
        if _peak > 0:
            _dd = (_peak - _running) / _peak * 100
            if _dd > _max_dd:
                _max_dd = _dd
    
    # Drawdown limit from settings
    _dd_limit = float(_db.load_setting("max_drawdown", "5.0"))
    
    # Health status
    _health = "good"
    _health_reason = "All systems operational"
    if ee.balance <= 0:
        _health = "critical"
        _health_reason = "Balance exhausted"
    elif _max_dd >= _dd_limit:
        _health = "warning"
        _health_reason = f"Drawdown {_max_dd:.1f}% exceeds limit {_dd_limit}%"
    elif len(ee.active_positions) > 5:
        _health = "warning"
        _health_reason = f"{len(ee.active_positions)} open positions"
    
    # Uptime
    _uptime = int(time.time() - getattr(get_status, "_start_time", time.time()))
    
    return {'''

if old_get_status in c:
    c = c.replace(old_get_status, new_get_status)
    print("Enhanced /api/status with today_pnl, win/loss, drawdown, health, uptime")
else:
    print("WARNING: old_get_status pattern not found!")

# Add the new fields to the return dict
old_return_start = '''        "trading_mode": getattr(orchestrator.execution_engine, "trading_mode", "paper"),
        "open_positions": len(orchestrator.execution_engine.active_positions),
        "holdings": holdings,
        "fiat_breakdown": fiat_breakdown,
    }'''

new_return_start = '''        "trading_mode": getattr(orchestrator.execution_engine, "trading_mode", "paper"),
        "open_positions": len(orchestrator.execution_engine.active_positions),
        "holdings": holdings,
        "fiat_breakdown": fiat_breakdown,
        "today_pnl": round(_today_pnl, 2),
        "today_pnl_pct": round(_today_pnl_pct, 2),
        "today_trade_count": len(_today_trades),
        "win_count": _win_count,
        "loss_count": _loss_count,
        "max_drawdown_pct": round(_max_dd, 2),
        "drawdown_limit": _dd_limit,
        "health_status": _health,
        "health_reason": _health_reason,
        "uptime_seconds": _uptime,
    }'''

if old_return_start in c:
    c = c.replace(old_return_start, new_return_start)
    print("Added new fields to return dict")
else:
    print("WARNING: return dict pattern not found!")

# Add startup time tracker
startup_marker = '''def get_status():
    import datetime, os as _os'''
if startup_marker in c:
    tracker = '''    if not hasattr(get_status, "_start_time"):
        get_status._start_time = time.time()
'''
    c = c.replace(startup_marker, startup_marker + "\n" + tracker)
    print("Added uptime tracker")

try:
    compile(c, "main.py", "exec")
    print("main.py syntax OK")
    with open("main.py", "w") as f:
        f.write(c)
    print("Saved main.py")
except SyntaxError as e:
    print(f"main.py SYNTAX ERROR: {e}")

# ============================================================
# 2. FRONTEND: Rewrite pollKpiPnL to update ALL KPIs
# ============================================================
os.chdir("/root/nexustrader/dashboard")

with open("enhancer.js") as f:
    ej = f.read()

# Find pollKpiPnL and replace entirely
old_poll = '''    function pollKpiPnL() {
        fetch('/api/status')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (d.total_pnl === undefined) return;
                var el = document.getElementById('val-total-pnl');
                if (!el) return;
                var prefix = d.total_pnl >= 0 ? '+' : '';
                el.textContent = prefix + '$' + Number(d.total_pnl).toFixed(2);
                el.className = d.total_pnl >= 0 ? 'kpi-value color-green' : 'kpi-value color-red';
                
                var sub = document.getElementById('val-total-pnl-percent');
                if (sub && d.initial_balance > 0) {
                    var pct = (d.total_pnl / d.initial_balance) * 100;
                    sub.textContent = prefix + pct.toFixed(2) + '%';
                    sub.className = d.total_pnl >= 0 ? 'kpi-sub color-green' : 'kpi-sub color-red';
                }
                
                // Update active positions KPI
                var elActive = document.getElementById('val-active-positions');
                if (elActive) {
                    elActive.textContent = 'Active: ' + (d.open_positions || 0);
                }
                
                // Update Mode badge
                var elMode = document.getElementById('val-mode-badge');
                if (elMode && d.trading_mode) {
                    elMode.textContent = d.trading_mode.toUpperCase();
                    elMode.className = 'mode-badge-' + d.trading_mode;
                }
                
                // Update cash balance with fiat breakdown
                var elCash = document.getElementById('val-cash-balance');
                if (elCash && d.fiat_breakdown) {
                    var parts = [];
                    if (d.fiat_breakdown.EUR) parts.push('EUR ' + Number(d.fiat_breakdown.EUR).toFixed(2));
                    if (d.fiat_breakdown.USD) parts.push('$' + Number(d.fiat_breakdown.USD).toFixed(2));
                    if (d.fiat_breakdown.GBP) parts.push('GBP ' + Number(d.fiat_breakdown.GBP).toFixed(2));
                    if (parts.length > 0) {
                        elCash.textContent = parts.join(' + ');
                    }
                }
            })
            .catch(function(err) { console.error('[ENHANCER] KPI poll error:', err); });'''

new_poll = r'''    function pollKpiPnL() {
        fetch('/api/status')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d) return;
                
                var hasInit = (typeof initialBalance !== 'undefined') ? initialBalance > 0 : false;
                var initBal = hasInit ? initialBalance : (d.balance || 0);
                
                // --- TOP ROW KPIs ---
                
                // 1. Total Portfolio Value (equity)
                setEl('val-equity', '$' + Number(d.equity || 0).toLocaleString(undefined, {minimumFractionDigits:2}));
                
                // 2. Cash Ready to Invest (balance)
                setEl('val-balance', '$' + Number(d.balance || 0).toLocaleString(undefined, {minimumFractionDigits:2}));
                
                // Active Trade Profit sub
                var unrealPnl = Number(d.equity || 0) - Number(d.balance || 0);
                var unrealPct = d.balance > 0 ? (unrealPnl / d.balance * 100) : 0;
                var upnlEl = document.getElementById('val-unrealized-pnl');
                if (upnlEl) {
                    upnlEl.textContent = 'Active Trade Profit: ' + (unrealPnl >= 0 ? '+' : '') + '$' + unrealPnl.toFixed(2) + ' (' + (unrealPnl >= 0 ? '+' : '') + unrealPct.toFixed(2) + '%)';
                    upnlEl.style.color = unrealPnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
                }
                
                // 3. Success Rate (top row val-winrate)
                var wr = d.closed_trades > 0 ? (d.win_count / d.closed_trades * 100) : 0;
                setEl('val-winrate', wr.toFixed(1) + '%');
                setEl('val-trade-count', d.closed_trades + ' trades completed');
                
                // 4. Total Profit
                var pnl = Number(d.total_pnl || 0);
                var prefix = pnl >= 0 ? '+' : '';
                setEl('val-total-pnl', prefix + '$' + pnl.toFixed(2), pnl >= 0 ? 'color-green' : 'color-red');
                
                // Total PnL percent
                var pnlPct = initBal > 0 ? (pnl / initBal * 100) : 0;
                var pnlSub = document.getElementById('val-total-pnl-percent');
                if (pnlSub) {
                    pnlSub.textContent = prefix + pnlPct.toFixed(2) + '% growth';
                    pnlSub.className = pnl >= 0 ? 'kpi-sub color-green' : 'kpi-sub color-red';
                }
                
                // 5. Max Drawdown
                var dd = Number(d.max_drawdown_pct || 0);
                setEl('val-max-drawdown', dd.toFixed(1) + '%', 'color-red');
                setEl('val-max-drawdown-limit', 'Limit: ' + Number(d.drawdown_limit || 5).toFixed(1) + '%');
                
                // --- BOTTOM ROW KPIs ---
                
                // Cash Balance (bottom)
                var fb = d.fiat_breakdown || {};
                var parts = [];
                if (fb.EUR) parts.push('EUR ' + Number(fb.EUR).toFixed(2));
                if (fb.USD) parts.push('$' + Number(fb.USD).toFixed(2));
                if (parts.length > 0) {
                    setEl('val-cash-balance', parts.join(' + '));
                } else {
                    setEl('val-cash-balance', '$' + Number(d.balance || 0).toFixed(2));
                }
                
                // Cash equity sub
                setEl('val-cash-equity', 'Equity: $' + Number(d.equity || 0).toFixed(2));
                
                // Fiat breakdown sub
                var fiatSub = document.getElementById('val-fiat-breakdown');
                if (fiatSub && fb) {
                    var fbParts = [];
                    if (fb.USD) fbParts.push('$' + Number(fb.USD).toFixed(2) + ' USD');
                    if (fb.EUR) fbParts.push('EUR ' + Number(fb.EUR).toFixed(2));
                    if (fb.GBP) fbParts.push('GBP ' + Number(fb.GBP).toFixed(2));
                    fiatSub.textContent = fbParts.join('  |  ') || '';
                }
                
                // Today PnL
                var todayPnl = Number(d.today_pnl || 0);
                var todayPrefix = todayPnl >= 0 ? '+' : '';
                var todayColor = todayPnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
                var todayEl = document.getElementById('val-today-pnl');
                if (todayEl) {
                    todayEl.textContent = todayPrefix + '$' + todayPnl.toFixed(2);
                    todayEl.style.color = todayColor;
                }
                var todaySub = document.getElementById('val-today-pnl-percent');
                if (todaySub) {
                    todaySub.textContent = todayPrefix + Number(d.today_pnl_pct || 0).toFixed(2) + '%';
                    todaySub.style.color = todayColor;
                }
                
                // Win Rate (bottom)
                setEl('val-win-rate', wr.toFixed(1) + '%');
                setEl('val-win-loss', (d.win_count || 0) + 'W / ' + (d.loss_count || 0) + 'L');
                
                // Total Trades
                setEl('val-total-trades', d.closed_trades || 0);
                setEl('val-active-positions', 'Active: ' + (d.open_positions || 0));
                
                // Health
                var h = d.health_status || 'good';
                var hLabel = 'GOOD';
                var hColor = 'var(--neon-green)';
                if (h === 'warning') { hLabel = 'WARNING'; hColor = 'var(--neon-orange)'; }
                if (h === 'critical') { hLabel = 'CRITICAL'; hColor = 'var(--neon-red)'; }
                var hEl = document.getElementById('val-health-status');
                if (hEl) {
                    hEl.textContent = hLabel;
                    hEl.style.color = hColor;
                }
                
                // Uptime
                var uptime = Number(d.uptime_seconds || 0);
                var utStr = '';
                if (uptime >= 86400) utStr = Math.floor(uptime / 86400) + 'd ' + Math.floor((uptime % 86400) / 3600) + 'h';
                else if (uptime >= 3600) utStr = Math.floor(uptime / 3600) + 'h ' + Math.floor((uptime % 3600) / 60) + 'm';
                else if (uptime >= 60) utStr = Math.floor(uptime / 60) + 'm ' + Math.floor(uptime % 60) + 's';
                else utStr = uptime + 's';
                setEl('val-uptime', 'Uptime: ' + utStr);
                
                // Mode badge
                var elMode = document.getElementById('val-mode-badge');
                if (elMode && d.trading_mode) {
                    elMode.textContent = d.trading_mode.toUpperCase();
                    elMode.className = 'mode-badge-' + d.trading_mode;
                }
            })
            .catch(function(err) { console.error('[ENHANCER] KPI poll error:', err); });'''

# Helper function for KPI element setting
helper = r'''
    // ============= KPI HELPER =============
    function setEl(id, text, cls) {
        var el = document.getElementById(id);
        if (!el) return;
        if (text !== undefined && text !== null) el.textContent = text;
        if (cls) {
            el.className = el.className.split(' ')[0] + ' ' + cls;
        }
    }

'''

# Insert helper and replace pollKpiPnL
if old_poll in ej:
    ej = ej.replace(old_poll, new_poll)
    print("Replaced pollKpiPnL with comprehensive version")
else:
    print("WARNING: old pollKpiPnL pattern not found")
    # Find it
    idx = ej.find("function pollKpiPnL")
    if idx >= 0:
        print(f"Found at {idx}: {ej[idx:idx+50]}")

# Insert setEl helper before pollKpiPnL
idx = ej.find("function pollKpiPnL")
if idx >= 0:
    ej = ej[:idx] + helper + ej[idx:]
    print("Inserted setEl helper")

# Add risk profile handler as backup
boot_idx = ej.find("function boot()")
if boot_idx >= 0:
    risk_handler = r'''
    // ============= RISK PROFILE HANDLER =============
    var _riskSelect = document.getElementById('risk-mode-select');
    if (_riskSelect && !_riskSelect.__enhancerBound) {
        _riskSelect.__enhancerBound = true;
        _riskSelect.addEventListener('change', function(e) {
            fetch('/api/system/risk_mode?risk_mode=' + encodeURIComponent(e.target.value), { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(d) { console.log('[ENHANCER] Risk updated:', d); })
                .catch(function(err) { console.error('[ENHANCER] Risk error:', err); });
        });
    }

'''
    ej = ej[:boot_idx] + risk_handler + ej[boot_idx:]
    print("Added risk profile handler backup")

with open("enhancer.js", "w") as f:
    f.write(ej)
print("Saved enhancer.js")

# Bump version
os.chdir("/root/nexustrader/dashboard")
with open("index.html") as f:
    html = f.read()
html = html.replace("enhancer.js?v=3.0", "enhancer.js?v=3.1")
with open("index.html", "w") as f:
    f.write(html)
print("Bumped to v=3.1")

print("\n=== ALL DONE ===")
