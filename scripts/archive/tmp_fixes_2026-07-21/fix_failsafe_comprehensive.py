import re

with open("/root/nexustrader/dashboard/index.html") as f:
    html = f.read()

# Replace everything from the first "<script>\n// KPI failsafe" to the last "</script>\n</body>"
start_marker = "<script>\n// KPI failsafe: polls /api/status directly, independent of enhancer.js"
end_marker = "</script>\n</body>"

start_idx = html.find(start_marker)
end_idx = html.rfind("</script>\n</body>")

if start_idx >= 0 and end_idx >= 0:
    new_scripts = """<script>
// FAILSAFE — Polls KPI, reasoning, and creates chart (independent of enhancer.js)
(function() {
    'use strict';
    
    // ============= KPI POLLING =============
    function updateKpis() {
        fetch("/api/status", { cache: "no-store" })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d || d.total_pnl === undefined) return;
                function s(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }
                function sc(id, c) { var el = document.getElementById(id); if (el) el.style.color = c; }
                
                s("val-equity", "$" + Number(d.equity).toFixed(2));
                s("val-balance", "$" + Number(d.balance).toFixed(2));
                s("val-total-pnl", (d.total_pnl >= 0 ? "+" : "") + "$" + Number(d.total_pnl).toFixed(2));
                var pnlEl = document.getElementById("val-total-pnl");
                if (pnlEl) pnlEl.className = d.total_pnl >= 0 ? "kpi-value color-green" : "kpi-value color-red";
                
                if (d.initial_balance && d.initial_balance > 0) {
                    var pct = (d.total_pnl / d.initial_balance) * 100;
                    s("val-total-pnl-percent", (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%");
                }
                
                var closed = d.closed_trades || 0;
                var won = d.winning_trades || 0;
                s("val-winrate", (closed > 0 ? (won / closed * 100).toFixed(1) : "0.0") + "%");
                s("val-trade-count", closed + " trades completed");
                s("val-cash-balance", "$" + Number(d.balance).toFixed(2));
                s("val-cash-equity", "Equity: $" + Number(d.equity).toFixed(2));
                
                var dpnl = d.daily_pnl || 0;
                s("val-today-pnl", (dpnl >= 0 ? "+" : "") + "$" + Number(dpnl).toFixed(2));
                sc("val-today-pnl", dpnl >= 0 ? "var(--neon-green)" : "var(--neon-red)");
                s("val-today-pnl-percent", (d.daily_pnl_pct || 0).toFixed(2) + "%");
                sc("val-today-pnl-percent", (d.daily_pnl_pct || 0) >= 0 ? "var(--neon-green)" : "var(--neon-red)");
                
                var losses = closed - won;
                s("val-win-rate", closed > 0 ? Math.round(won / closed * 100) + "%" : "0%");
                s("val-win-loss", won + "W / " + losses + "L");
                s("val-total-trades", closed);
                s("val-active-positions", "Active: " + (d.open_positions || 0));
                
                if (d.max_drawdown !== null && d.max_drawdown !== undefined) {
                    s("val-max-drawdown", Number(d.max_drawdown).toFixed(1) + "%");
                }
                
                // Also update reasoning
                updateReasoning();
            })
            .catch(function(err) { console.warn("[FAILSAFE] KPI error:", err); });
    }
    
    // ============= TRADING REASONING =============
    function updateReasoning() {
        fetch("/api/trading/reasoning", { cache: "no-store" })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var el = document.getElementById("reasoning-text");
                if (!el) return;
                if (!d.reasons || d.reasons.length === 0) {
                    el.textContent = "Bot is operating normally.";
                    return;
                }
                var html = "";
                for (var i = 0; i < d.reasons.length; i++) {
                    var r = d.reasons[i];
                    var icon = r.type === "success" ? "\\u2705" : r.type === "warning" ? "\\u26a0\\ufe0f" : r.type === "critical" ? "\\ud83d\\udd34" : r.type === "error" ? "\\u274c" : "\\u2139\\ufe0f";
                    var color = r.type === "success" ? "var(--neon-green)" : r.type === "warning" ? "var(--neon-orange)" : r.type === "critical" ? "var(--neon-red)" : r.type === "error" ? "var(--neon-red)" : "var(--text-secondary)";
                    html += '<div style="margin-bottom:6px;font-size:12px;line-height:1.4;"><span style="color:' + color + ';">' + icon + "</span> <span>" + r.message + "</span></div>";
                }
                el.innerHTML = html;
                
                // Show reasoning panel
                var panel = document.getElementById("reasoning-panel");
                if (panel) panel.style.display = "block";
            })
            .catch(function() {});
    }
    
    // ============= CHART =============
    var chartInstance = null;
    var candlestickSeries = null;
    var chartTimeframe = "1h";
    var activeTicker = "";
    
    function initChart() {
        if (typeof LightweightCharts === "undefined") {
            console.warn("[FAILSAFE] LightweightCharts not loaded yet, retrying...");
            setTimeout(initChart, 2000);
            return;
        }
        var canvas = document.getElementById("main-chart");
        if (!canvas) return;
        
        // Check if enhancer.js already created chart
        var parent = canvas.parentNode;
        var container = parent.closest ? parent.closest(".chart-container") : null;
        if (!container) container = document.querySelector(".chart-container");
        if (!container) return;
        
        // If enhancer wrapped canvas, bail
        if (parent !== container) {
            console.log("[FAILSAFE] enhancer.js chart detected, skipping");
            return;
        }
        
        console.log("[FAILSAFE] Creating LightweightCharts chart");
        canvas.style.display = "none";
        
        chartInstance = LightweightCharts.createChart(container, {
            layout: { background: {type:"solid",color:"transparent"}, textColor:"#94a3b8" },
            grid: { vertLines:{color:"rgba(255,255,255,0.03)"}, horzLines:{color:"rgba(255,255,255,0.03)"} },
            width: container.clientWidth || container.offsetWidth || 600,
            height: 350,
            timeScale: { timeVisible: true, secondsVisible: false },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        });
        
        candlestickSeries = chartInstance.addCandlestickSeries({
            upColor:"#22c55e", downColor:"#ef4444",
            borderDownColor:"#ef4444", borderUpColor:"#22c55e",
            wickDownColor:"#ef4444", wickUpColor:"#22c55e",
        });
        
        chartInstance.addHistogramSeries({
            priceFormat: { type: "volume" },
            priceScaleId: "volume",
        });
        chartInstance.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
        
        // Resize handler
        window.addEventListener("resize", function() {
            var w = container.clientWidth || container.offsetWidth;
            if (w > 0 && chartInstance) chartInstance.applyOptions({ width: w });
        });
        
        // Fetch chart data
        setTimeout(fetchChartData, 1000);
        setInterval(fetchChartData, 60000);
    }
    
    function fetchChartData() {
        if (!candlestickSeries) return;
        
        // Get active ticker from enhancer override or window
        var ticker = activeTicker || (window.__REST_INIT && window.__REST_INIT.ticker) || "";
        if (!ticker) {
            // Try to get from the first ticker tab
            var tab = document.querySelector(".ticker-tab");
            if (tab) ticker = tab.textContent.trim();
        }
        if (!ticker) { console.log("[FAILSAFE] No ticker yet"); return; }
        activeTicker = ticker;
        
        fetch("/api/history?symbol=" + encodeURIComponent(ticker) + "&tf=" + chartTimeframe + "&limit=100", { cache: "no-store" })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data || !data.length) return;
                var candles = [], volumes = [];
                for (var i = 0; i < data.length; i++) {
                    var d = data[i];
                    candles.push({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close });
                    volumes.push({ time: d.time, value: d.volume || 0, color: d.close >= d.open ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)" });
                }
                candlestickSeries.setData(candles);
            })
            .catch(function(err) { console.warn("[FAILSAFE] Chart data error:", err); });
    }
    
    // Timeframe button click handler
    document.addEventListener("click", function(e) {
        var btn = e.target.closest ? e.target.closest(".tf-btn") : null;
        if (btn && btn.dataset && btn.dataset.tf) {
            chartTimeframe = btn.dataset.tf;
            document.querySelectorAll(".tf-btn").forEach(function(b) {
                b.classList.toggle("active", b.dataset.tf === chartTimeframe);
            });
            fetchChartData();
        }
    });
    
    // Expose fetchChartData for ticker switches
    window.__failsafeFetchChart = fetchChartData;
    window.__failsafeSetTicker = function(t) { activeTicker = t; setTimeout(fetchChartData, 500); };
    
    // ============= BOOT =============
    function boot() {
        console.log("[FAILSAFE] booting");
        setTimeout(updateKpis, 500);
        setTimeout(updateKpis, 3000);
        setInterval(updateKpis, 10000);
        setTimeout(initChart, 1000);
    }
    
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
</script>
</body>"""

    html = html[:start_idx] + new_scripts
    with open("/root/nexustrader/dashboard/index.html", "w") as f:
        f.write(html)
    print("OK - Comprehensive failsafe injected")
else:
    print("FAIL - markers not found")
    print("start at", start_idx)
    print("end at", end_idx)
