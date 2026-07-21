/**
 * enhancer.js v2.0 — REST init fallback + LightweightCharts + Trade Polling + Eval Widget
 * Self-contained: fetches /api/init directly, polls trades every 10s, updates eval widget.
 * Calls window.handleInitState (exported from app_v2.js).
 */
(function() {
    'use strict';
    
    console.log('[ENHANCER] booting v2.0');
    
    var lineSeries = null;
    var volumeSeries = null;
    var chartInstance = null;
    var chartResizeHandler = null;
    var chartTimeframe = '1h';
    var lastTradeCount = 0;
    var lastPositions = [];
    
    // ============= LIGHTWEIGHTCHARTS =============
    function initLwChart() {
        var canvas = document.getElementById('main-chart');
        if (!canvas) { console.warn('[ENHANCER] main-chart not found'); return; }
        
        try {
            var wrap = document.createElement('div');
            wrap.style.cssText = 'height:350px;width:100%;position:relative;overflow:hidden;';
            canvas.parentNode.insertBefore(wrap, canvas);
            wrap.appendChild(canvas);
            canvas.style.display = 'none';
            
            if (typeof LightweightCharts === 'undefined') {
                console.warn('[ENHANCER] LightweightCharts not loaded');
                return;
            }
            
            chartInstance = LightweightCharts.createChart(wrap, {
                layout: {
                    background: { type: 'solid', color: 'transparent' },
                    textColor: '#94a3b8',
                },
                grid: {
                    vertLines: { color: 'rgba(255,255,255,0.03)' },
                    horzLines: { color: 'rgba(255,255,255,0.03)' },
                },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
                timeScale: {
                    borderColor: 'rgba(255,255,255,0.08)',
                    timeVisible: true,
                    secondsVisible: false,
                },
                width: wrap.clientWidth || 600,
                height: 350,
            });
            
            lineSeries = chartInstance.addLineSeries({
                color: '#22c55e',
                lineWidth: 2,
                crosshairMarkerVisible: true,
                priceFormat: { type: 'price' },
            });
            
            volumeSeries = chartInstance.addAreaSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: 'volume',
            });
            chartInstance.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
            
            window.removeEventListener('resize', chartResizeHandler);
            chartResizeHandler = function() {
                var w = wrap.clientWidth;
                if (w > 0 && chartInstance) chartInstance.applyOptions({ width: w });
            };
            window.addEventListener('resize', chartResizeHandler);
            
            console.log('[ENHANCER] LightweightCharts ready');
        } catch(e) {
            console.error('[ENHANCER] Chart error:', e);
        }
    }
    
    function fetchChartData(ticker, tf) {
        if (!ticker) ticker = window.activeTicker || '';
        if (!tf) tf = chartTimeframe;
        if (!ticker || !lineSeries) return;
        
        document.querySelectorAll('.tf-btn').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.tf === tf);
        });
        
        fetch('/api/history?symbol=' + encodeURIComponent(ticker) + '&tf=' + encodeURIComponent(tf) + '&limit=100')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data || !data.length) return;
                var candles = [];
                for (var i = 0; i < data.length; i++) {
                    var d = data[i];
                    var ts = d.time || d.timestamp || 0;
                    if (typeof ts === "string") ts = Math.floor(new Date(ts).getTime() / 1000);
                    candles.push({ time: ts, value: d.close || d.price || 0 });
                }
                lineSeries.setData(candles);
                console.log('[ENHANCER] chart', candles.length, 'candles loaded');
            })
            .catch(function(err) { console.error('[ENHANCER] chart fetch err:', err); });
    }
    
    // ============= OVERRIDE switchTicker =============
    var origSwitchTicker = window.switchTicker;
    window.switchTicker = function(ticker) {
        if (typeof origSwitchTicker === 'function') origSwitchTicker(ticker);
        else window.activeTicker = ticker;
        fetchChartData(ticker, chartTimeframe);
    };
    
    // ============= KPI PNL =============
    
    // ============= KPI HELPER =============
    function setEl(id, text, cls) {
        var el = document.getElementById(id);
        if (!el) return;
        if (text !== undefined && text !== null) el.textContent = text;
        if (cls) {
            el.className = el.className.split(' ')[0] + ' ' + cls;
        }
    }

function pollKpiPnL() {
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
            .catch(function(err) { console.error('[ENHANCER] KPI poll error:', err); });
    }
    
    // ============= TRADE LOG POLLING =============
    function pollTrades() {
        fetch('/api/trades/all')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data || !data.trades || !data.trades.length) return;
                
                // Always refresh from API (API is truth source)
                lastTradeCount = data.trades.length;
                
                console.log('[ENHANCER] Trades updated:', data.trades.length);
                
                if (typeof window.renderTradeLog === 'function') {
                    window.renderTradeLog(data.trades);
                }
                
                // Also update KPI
                if (typeof window.updatePerformanceKPIs === 'function') {
                    window.updatePerformanceKPIs(data.trades, 0);
                }
            })
            .catch(function(err) { 
                // Silently retry - exchange calls may time out
            });
    }
    
    // ============= EVALUATION WIDGET UPDATE =============
    function pollSignals() {
        fetch('/api/trading/signals')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data) return;
                
                var ticker = window.activeTicker || '';
                var tickerData = ticker ? data[ticker] : null;
                if (!tickerData) {
                    // Pick the first ticker with a signal
                    var keys = Object.keys(data);
                    for (var i = 0; i < keys.length; i++) {
                        if (data[keys[i]].weighted_signal !== 0) {
                            tickerData = data[keys[i]];
                            break;
                        }
                    }
                }
                
                if (!tickerData) return;
                
                // Update evaluation widget values
                var ws = tickerData.weighted_signal || 0;
                var dir = tickerData.direction || 'NEUTRAL';
                
                var elBuy = document.getElementById('val-prob-buy');
                var elSell = document.getElementById('val-prob-sell');
                
                if (elBuy && elSell) {
                    if (dir === 'BULLISH') {
                        elBuy.textContent = '65%';
                        elSell.textContent = '35%';
                    } else if (dir === 'BEARISH') {
                        elBuy.textContent = '35%';
                        elSell.textContent = '65%';
                    } else {
                        elBuy.textContent = '50%';
                        elSell.textContent = '50%';
                    }
                }
                
                var elSig = document.getElementById('val-sig-strength');
                if (elSig) {
                    elSig.textContent = Math.round(Math.abs(ws) * 100) + '%';
                }
                
                // Update viability badge
                var elViability = document.getElementById('viability-badge');
                if (elViability) {
                    var absSig = Math.abs(ws);
                    if (absSig > 0.15) {
                        elViability.textContent = 'SIGNAL ACTIVE — ' + dir + ' (Strength: ' + Math.round(absSig * 100) + '%)';
                        elViability.style.background = 'rgba(16, 185, 129, 0.1)';
                        elViability.style.border = '1px solid var(--neon-green)';
                        elViability.style.color = 'var(--neon-green)';
                    } else if (absSig > 0.05) {
                        elViability.textContent = 'WEAK SIGNAL — ' + dir + ' (Strength: ' + Math.round(absSig * 100) + '%)';
                        elViability.style.background = 'rgba(251, 191, 36, 0.1)';
                        elViability.style.border = '1px solid #f59e0b';
                        elViability.style.color = '#f59e0b';
                    } else {
                        elViability.textContent = 'NO CLEAR SIGNAL — AWAITING SETUP';
                        elViability.style.background = 'rgba(255,255,255,0.02)';
                        elViability.style.border = '1px solid rgba(255,255,255,0.08)';
                        elViability.style.color = 'var(--text-muted)';
                    }
                }
            })
            .catch(function(err) { console.error('[ENHANCER] signal poll error:', err); });
    }
    
    // ============= REST INIT =============
    function tryRestInit() {
        if (window.completedTrades && window.completedTrades.length > 0) {
            console.log('[ENHANCER] already inited via WS');
            loadChart();
            return;
        }
        
        var data = window.__REST_INIT;
        if (data) {
            doInit(data);
            return;
        }
        
        console.log('[ENHANCER] fetching /api/init...');
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/api/init', true);
        xhr.timeout = 10000;
        xhr.onload = function() {
            if (xhr.status === 200) {
                try {
                    doInit(JSON.parse(xhr.responseText));
                } catch(e) {
                    console.error('[ENHANCER] parse error:', e);
                    setTimeout(tryRestInit, 2000);
                }
            } else {
                console.warn('[ENHANCER] /api/init status:', xhr.status);
                setTimeout(tryRestInit, 2000);
            }
        };
        xhr.onerror = function() {
            console.warn('[ENHANCER] /api/init failed, retrying...');
            setTimeout(tryRestInit, 2000);
        };
        xhr.ontimeout = function() {
            console.warn('[ENHANCER] /api/init timeout, retrying...');
            setTimeout(tryRestInit, 2000);
        };
        xhr.send();
    }
    
    function doInit(data) {
        if (typeof window.handleInitState === 'function') {
            try {
                console.log('[ENHANCER] calling handleInitState');
                window.handleInitState(data);
                console.log('[ENHANCER] handleInitState done');
            } catch(e) {
                console.error('[ENHANCER] handleInitState error:', e);
            }
        } else {
            console.warn('[ENHANCER] handleInitState not ready, retrying...');
            setTimeout(tryRestInit, 1000);
            return;
        }
        // After init, fetch trades to set baseline count
        fetch('/api/trades/all')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (d && d.trades) lastTradeCount = d.trades.length;
            })
            .catch(function() {});
        loadChart();
    }
    
    function loadChart() {
        var ticker = window.activeTicker || 
            (window.__REST_INIT && window.__REST_INIT.ticker) || '';
        if (ticker) setTimeout(function() { fetchChartData(ticker, chartTimeframe); }, 500);
    }
    
    // ============= EVENTS =============
    function bindEvents() {
        document.addEventListener('click', function(e) {
            var btn = e.target.closest ? e.target.closest('.tf-btn') : null;
            if (btn && btn.dataset && btn.dataset.tf) {
                chartTimeframe = btn.dataset.tf;
                fetchChartData(window.activeTicker, chartTimeframe);
            }
        });
    }
    
    // ============= BOOT =============

    // ============= RENDER OPEN POSITIONS IN TRADES TABLE =============
    window.renderOpenPositions = function(positions) {
        var tbody = document.getElementById('recent-trades-list');
        if (!tbody) return;
        
        // Remove any existing open-position rows
        var existing = tbody.querySelectorAll('.open-position-row');
        for (var i = 0; i < existing.length; i++) {
            existing[i].remove();
        }
        
        if (!positions || positions.length === 0) return;
        
        // Insert open positions at the top of the table
        for (var p = 0; p < positions.length; p++) {
            var pos = positions[p];
            var row = document.createElement("tr");
            row.className = "open-position-row";
            row.style.cssText = "background: rgba(16, 185, 129, 0.08); border-left: 3px solid var(--neon-green);";
            
            var entryD = new Date(pos.entry_time * 1000);
            var dateStr = entryD.toLocaleDateString([], { month: "short", day: "numeric" });
            var timeStr = entryD.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            var sideColor = pos.direction === "BUY" ? "var(--neon-green)" : "var(--neon-red)";
            var pnlColor = pos.unrealized_pnl >= 0 ? "var(--neon-green)" : "var(--neon-red)";
            var pnlSign = pos.unrealized_pnl >= 0 ? "+" : "";
            
            var ageStr = "";
            if (pos.age_seconds > 3600) {
                ageStr = Math.round(pos.age_seconds / 3600) + "h";
            } else if (pos.age_seconds > 60) {
                ageStr = Math.round(pos.age_seconds / 60) + "m";
            } else {
                ageStr = pos.age_seconds + "s";
            }
            
            row.innerHTML = [
                '<td style="font-weight:600;">', dateStr, '</td>',
                '<td style="font-weight:600;">', timeStr, '</td>',
                '<td style="font-weight:600;">', pos.symbol, '</td>',
                '<td style="color:', sideColor, '; font-weight:600;">', pos.direction, ' <span style="font-size:10px;color:var(--text-muted);">', ageStr, '</span></td>',
                '<td>', pos.quantity.toFixed(4), '</td>',
                '<td>$', pos.entry_price.toFixed(4), '</td>',
                '<td style="color:var(--neon-blue);font-weight:600;">$', pos.current_price.toFixed(4), '</td>',
                '<td class="', pnlColor === "var(--neon-green)" ? "color-green" : "color-red", '" style="font-weight:600;">', pnlSign, '$', pos.unrealized_pnl.toFixed(2), ' (', pos.unrealized_pnl_pct.toFixed(1), '%)</td>',
                '<td><span style="background: rgba(16, 185, 129, 0.2); color: var(--neon-green); padding: 4px 8px; border-radius: 4px; font-size:11px; font-weight:600;">OPEN</span></td>',
            ].join("");
            
            // Insert at top of tbody
            if (tbody.firstChild) {
                tbody.insertBefore(row, tbody.firstChild);
            } else {
                tbody.appendChild(row);
            }
        }
    };
    
    function pollPositions() {
        fetch('/api/positions')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data) return;
                var positions = data.positions || [];
                var fb = data.fiat_breakdown || {};
                var cryptoCount = data.crypto_asset_count || 0;
                
                // Update active tactical position card
                var container = document.getElementById('position-details-container');
                if (container) {
                    var html = '';
                    if (positions && positions.length > 0) {
                        // Show active position
                        var pos = positions[0];
                        var sideClass = pos.direction === "BUY" ? "color-green" : "color-red";
                        var pnlClass = pos.unrealized_pnl >= 0 ? "color-green" : "color-red";
                        var pnlIcon = pos.unrealized_pnl >= 0 ? "&#9650;" : "&#9660;";
                        html = '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Symbol</span><br><strong>' + pos.symbol + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Direction</span><br><strong class="' + sideClass + '">' + pos.direction + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Entry</span><br><strong>$' + pos.entry_price.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Current</span><br><strong>$' + pos.current_price.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Qty</span><br><strong>' + pos.quantity.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Unrealized PnL</span><br><strong class="' + pnlClass + '">' + pnlIcon + ' $' + pos.unrealized_pnl.toFixed(2) + ' (' + pos.unrealized_pnl_pct.toFixed(2) + '%)</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">TP</span><br><strong>$' + pos.take_profit.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">SL</span><br><strong>$' + pos.stop_loss.toFixed(4) + '</strong></div>';
                        html += '</div>';
                    } else {
                        // Show fiat holdings breakdown
                        html = '<p style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 5px; margin: 0 0 8px 0;">No Active Trading Position</p>';
                        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">';
                        var hasFiat = false;
                        for (var cur in fb) {
                            hasFiat = true;
                            html += '<div style="background: rgba(255,255,255,0.04); border-radius: 6px; padding: 8px; text-align: center;">';
                            html += '<div style="font-size: 10px; color: var(--text-muted);">' + cur + '</div>';
                            html += '<div style="font-size: 18px; font-weight: 700; color: var(--neon-blue);">$' + Number(fb[cur]).toFixed(2) + '</div>';
                            html += '</div>';
                        }
                        if (cryptoCount > 0) {
                            html += '<div style="grid-column: 1 / -1; font-size: 11px; color: var(--text-muted); text-align: center; border-top: 1px solid var(--border-color); padding-top: 8px; margin-top: 4px;">';
                            html += 'Portfolio: ' + cryptoCount + ' crypto assets</div>';
                        }
                        html += '</div>';
                    }
                    container.innerHTML = html;
                }
                
                // Render at top of trades table
                if (typeof window.renderOpenPositions === "function") {
                    window.renderOpenPositions(positions);
                }
            })
            .catch(function(err) {
                console.error("[ENHANCER] pollPositions:", err);
            });
    }
    

    
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

function boot() {
        initLwChart();
        bindEvents();
        
        var waitForExport = setInterval(function() {
            if (typeof window.handleInitState === 'function') {
                clearInterval(waitForExport);
                console.log('[ENHANCER] handleInitState available');
                tryRestInit();
            }
        }, 100);
        
        // Poll KPIs every 5s
        setInterval(pollKpiPnL, 5000);
        setTimeout(pollKpiPnL, 100);
        
        // Poll trades every 10s (auto-update trade log without WS)
        setInterval(pollTrades, 10000);
        
        // Poll positions every 5s (open positions + fiat holdings)
        setInterval(pollPositions, 5000);
        setTimeout(pollPositions, 200);
        
        // Poll signals every 5s (update eval widget)
        setInterval(pollSignals, 5000);
        
        console.log('[ENHANCER] booted v2.0');
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
    // ─── Quant Team ────────────────────────────────────────────────────────────
    window.pollQuantTeam = function() {
        xhr('GET', '/api/quant/status', function(resp) {
            try {
                var data = JSON.parse(resp);
                if (!data.agents) return;
                var agents = data.agents;

                agents.forEach(function(a) {
                    var statusEl = document.getElementById('quant-status-' + a.id);
                    if (statusEl) {
                        if (a.last_report) {
                            var d = new Date(a.last_report * 1000);
                            var ago = Math.floor((Date.now() - d.getTime()) / 3600000);
                            statusEl.innerHTML = '<span style="color:var(--neon-green);">●</span> Last run: ' + (ago < 24 ? ago + 'h ago' : d.toLocaleDateString());
                            statusEl.title = a.last_report_summary || '';
                        } else {
                            statusEl.innerHTML = '<span style="color:var(--text-muted);">●</span> Awaiting first run';
                        }
                    }
                });
            } catch(e) { console.error('quant status parse error:', e); }
        });
    };

    // Pre-fill prompts with defaults if not already set
    window.loadDefaultPrompts = function() {
        var defaults = {
            'prompt-quant-text': 'Analyze recent trades to optimize TP/SL multipliers, signal threshold, and learning rate. Focus on: win rate above 40%, Sharpe ratio trending positive, monthly PnL green. Never widen SL beyond 5x ATR. Keep signal threshold between 0.35-0.65.',
            'prompt-sentiment-text': 'Scan crypto news headlines, social media volume, and fear/greed indicators for active tickers. Score each asset from -1 (extreme fear) to +1 (extreme greed). Flag extreme readings (>0.7 or <-0.7) for position size adjustment.',
            'prompt-risk-text': 'Audit all open positions and recent trades for risk violations: max drawdown vs limit, position concentration, correlation clustering, risk of ruin. If any metric exceeds threshold, recommend reducing position sizes or entering cooldown.',
            'prompt-allocator-text': 'Review per-ticker performance. Rebalance active tickers: increase allocation to winners, reduce/disable losers. Adjust Kelly ceilings based on volatility. Rotate capital. Max 9 tickers.',
            'prompt-dev-text': 'Review NexusTrader dashboard code at /root/nexustrader/dashboard/. Fix bugs in JS/CSS/HTML. Improve error handling. Never modify main.py trading logic. Always backup files before editing.',
            'prompt-asset-selector-text': 'Scan Kraken API for all tradeable USD pairs. Filter by 24h volume > $1M, not stablecoin. Add up to 2 new high-potential assets. Disable delisted pairs. Always keep BTC-USD and ETH-USD.',
            'prompt-improve-text': 'Analyze last 200 trades. Identify which strategies contribute positive alpha. Evolve ensemble weights: boost winners, prune losers. Tune hyperparameters. Max 20% change per parameter per week.',
            'prompt-blog-text': 'Generate weekly performance report: total PnL, win rate, best/worst trades, drawdown, ticker ranking. Include text-based charts. Output to blog/daily_summaries/weekly_report_DATE.md.',
            'prompt-researcher-text': 'Deep monthly analysis: Sharpe, Sortino, Calmar ratios, max drawdown duration, profit factor. Segment by ticker, strategy, time-of-day. Recommend new strategies and risk framework upgrades.'
        };
        Object.keys(defaults).forEach(function(id) {
            var el = document.getElementById(id);
            if (el && !el.value.trim()) {
                el.value = defaults[id];
            }
        });
    };
    
    window.loadQuantPrompt = function() {
        xhr('GET', '/api/quant/prompt', function(resp) {
            try {
                var data = JSON.parse(resp);
                var ta = document.getElementById('prompt-quant-team-text');
                if (ta && data.prompt) {
                    ta.value = data.prompt;
                }
            } catch(e) {}
        });
    };

    window.saveQuantPrompt = function() {
        var ta = document.getElementById('prompt-quant-team-text');
        var status = document.getElementById('quant-prompt-status');
        if (!ta) return;
        var prompt = ta.value || '';
        xhr('POST', '/api/quant/prompt', function(resp) {
            try {
                var data = JSON.parse(resp);
                if (status) {
                    status.textContent = data.status === 'saved' ? '\u2713 Saved (' + data.length + ' chars)' : '\u2717 Error';
                    status.style.color = data.status === 'saved' ? 'var(--neon-green)' : 'var(--neon-red)';
                    setTimeout(function() { status.textContent = ''; }, 3000);
                }
            } catch(e) {}
        }, null, JSON.stringify({prompt: prompt}));
    };

    function bootQuantTeam() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootQuantTeam);
            return;
        }
        _runQuantTeam();
    }
    bootQuantTeam();
    
    function _runQuantTeam() {
        var triggers = {
            'trigger-opt-params-btn-tab': 'quant-optimizer',
            'trigger-sentiment-btn-tab': 'sentiment',
            'trigger-risk-audit-btn-tab': 'risk-auditor',
            'trigger-alloc-btn-tab': 'allocator',
            'trigger-self-dev-btn-tab': 'self-dev',
            'trigger-asset-selector-btn-tab': 'asset-selector',
            'trigger-self-improve-btn-tab': 'self-improve',
            'trigger-blog-btn-tab': 'blogger',
            'trigger-researcher-btn-tab': 'researcher'
        };
        Object.keys(triggers).forEach(function(btnId) {
            (function(bid) {
                var btn = document.getElementById(bid);
                if (btn) {
                    btn.dataset.origText = btn.textContent.trim();
                    btn.addEventListener('click', function() {
                        var agent = triggers[bid];
                        xhr('POST', '/api/quant/trigger', function(resp) {
                            try {
                                var data = JSON.parse(resp);
                                btn.textContent = data.status === 'requested' ? '\u2713 Requested' : '\u26a0 Error';
                                setTimeout(function() { btn.textContent = btn.dataset.origText; }, 2000);
                            } catch(e) {}
                        }, null, JSON.stringify({agent: agent}));
                    });
                }
            })(btnId);
        });

        var runAll = document.getElementById('btn-run-all-agents');
        if (runAll) {
            runAll.addEventListener('click', function() {
                xhr('POST', '/api/quant/trigger', function(resp) {
                    try {
                        var data = JSON.parse(resp);
                        runAll.textContent = '\u2713 All Requested';
                        setTimeout(function() {
                            runAll.innerHTML = '<i data-lucide="zap" style="width:14px;height:14px;"></i> Run All Agents';
                        }, 3000);
                    } catch(e) {}
                }, null, JSON.stringify({agent: 'all'}));
            });
        }

        var saveBtn = document.getElementById('btn-save-quant-prompt');
        if (saveBtn) {
            saveBtn.addEventListener('click', function() { window.saveQuantPrompt(); });
        }

        // Save All Agent Prompts button
        var saveAllPrompts = document.getElementById('save-prompts-btn');
        if (saveAllPrompts) {
            saveAllPrompts.addEventListener('click', function() {
                var prompts = {
                    'quant-optimizer': document.getElementById('prompt-quant-text'),
                    'sentiment': document.getElementById('prompt-sentiment-text'),
                    'risk-auditor': document.getElementById('prompt-risk-text'),
                    'allocator': document.getElementById('prompt-allocator-text'),
                    'self-dev': document.getElementById('prompt-dev-text'),
                    'asset-selector': document.getElementById('prompt-asset-selector-text'),
                    'self-improve': document.getElementById('prompt-improve-text'),
                    'blogger': document.getElementById('prompt-blog-text'),
                    'researcher': document.getElementById('prompt-researcher-text')
                };
                var saved = 0;
                Object.keys(prompts).forEach(function(k) {
                    var el = prompts[k];
                    if (el && el.value.trim()) {
                        xhr('POST', '/api/quant/prompt/save', function(){}, null,
                            JSON.stringify({agent: k, prompt: el.value}));
                        saved++;
                    }
                });
                saveAllPrompts.textContent = '\u2713 Saved ' + saved + ' prompts';
                setTimeout(function() {
                    saveAllPrompts.innerHTML = '<i data-lucide="save" style="width:16px;height:16px;margin-right:4px;"></i> Save All Agent Prompts';
                }, 2500);
            });
        }

        setTimeout(function() {
            window.pollQuantTeam();
            window.loadQuantPrompt();
            window.loadDefaultPrompts();
        }, 1000);

        setInterval(function() { window.pollQuantTeam(); }, 60000);
    }
        // Apply All Optimizations button
        var applyAllBtn = document.getElementById('btn-apply-all-optimizations');
        if (applyAllBtn) {
            applyAllBtn.addEventListener('click', function() {
                if (!confirm('Apply all pending optimizations? This will update TP/SL, thresholds, and strategy weights.')) return;
                applyAllBtn.disabled = true;
                applyAllBtn.textContent = 'Applying...';
                xhr('POST', '/api/optimizations/apply/all', function(resp) {
                    applyAllBtn.disabled = false;
                    applyAllBtn.innerHTML = '<i data-lucide="check-circle"></i> Apply All';
                    try {
                        var r = JSON.parse(resp || '{}');
                        if (r.status === 'ok') {
                            window.showToast && window.showToast('Applied ' + r.count + ' optimizations!', 'success');
                        } else {
                            window.showToast && window.showToast('Error: ' + (r.error || 'unknown'), 'error');
                        }
                    } catch(e) {}
                }, function(err) {
                    applyAllBtn.disabled = false;
                    applyAllBtn.innerHTML = '<i data-lucide="check-circle"></i> Apply All';
                    window.showToast && window.showToast('Apply failed: ' + err, 'error');
                });
            });
        }



        // ============================================================
        // LLM Tab handlers
        // ============================================================
        
        function initLLMTab() {
            pollLLMStatus();
            pollNNArchitecture();
        }
        
        function pollLLMStatus() {
            if (document.getElementById('llm-status')) {
                xhr('GET', '/api/llm/status', null, function(resp) {
                    var s = JSON.parse(resp);
                    var statusEl = document.getElementById('llm-status');
                    if (s.server_connected) {
                        statusEl.textContent = 'Connected';
                        statusEl.style.color = 'var(--neon-green)';
                    } else if (s.llm_enabled) {
                        statusEl.textContent = 'Enabled (no server)';
                        statusEl.style.color = 'var(--neon-orange)';
                    } else {
                        statusEl.textContent = 'Disabled';
                        statusEl.style.color = 'var(--neon-red)';
                    }
                    var servEl = document.getElementById('llm-server');
                    if (servEl) servEl.textContent = s.endpoint || 'not configured';
                });
            }
        }
        
        function pollNNArchitecture() {
            xhr('GET', '/api/nn/architecture', null, function(resp) {
                try {
                    var a = JSON.parse(resp);
                    var arch = a.architecture || 'mlp';
                    ['mlp', 'lstm', 'transformer'].forEach(function(name) {
                        var radio = document.querySelector('input[name="nn-arch"][value="' + name + '"]');
                        if (radio) radio.checked = (name === arch);
                        var label = document.getElementById('nn-opt-' + name);
                        if (label) {
                            if (name === arch) {
                                label.style.borderColor = 'var(--neon-blue)';
                                label.style.background = 'rgba(0,240,255,0.05)';
                            } else {
                                label.style.borderColor = 'var(--border-color)';
                                label.style.background = 'transparent';
                            }
                        }
                    });
                    var stat = document.getElementById('nn-arch-status');
                    if (stat && a.description) stat.textContent = 'Current: ' + arch.toUpperCase() + ' = ' + (a.description[arch] || '');
                } catch(e) {
                    console.error('NN arch poll error:', e);
                }
            });
        }
        
        document.querySelectorAll('input[name="nn-arch"]').forEach(function(radio) {
            radio.addEventListener('change', function() {
                ['mlp', 'lstm', 'transformer'].forEach(function(name) {
                    var label = document.getElementById('nn-opt-' + name);
                    if (label) {
                        label.style.borderColor = 'var(--border-color)';
                        label.style.background = 'transparent';
                    }
                });
                var checked = document.querySelector('input[name="nn-arch"]:checked');
                if (checked) {
                    var label = document.getElementById('nn-opt-' + checked.value);
                    if (label) {
                        label.style.borderColor = 'var(--neon-blue)';
                        label.style.background = 'rgba(0,240,255,0.05)';
                    }
                }
            });
        });
        
        var btnSaveNN = document.getElementById('btn-save-nn-arch');
        if (btnSaveNN) {
            btnSaveNN.addEventListener('click', function() {
                var checked = document.querySelector('input[name="nn-arch"]:checked');
                if (!checked) return;
                btnSaveNN.disabled = true;
                btnSaveNN.textContent = 'Saving...';
                xhr('POST', '/api/nn/architecture', JSON.stringify({architecture: checked.value}), function(resp) {
                    var r = JSON.parse(resp);
                    var status = document.getElementById('nn-arch-status');
                    if (r.ok) {
                        if (status) { status.textContent = 'SAVED: ' + r.architecture.toUpperCase() + '. Restart to apply.'; status.style.color = 'var(--neon-green)'; }
                        if (window.showToast) window.showToast('NN architecture set to ' + r.architecture.toUpperCase(), 'success');
                    } else {
                        if (status) { status.textContent = 'ERROR: ' + (r.error || 'unknown'); status.style.color = 'var(--neon-red)'; }
                    }
                    btnSaveNN.disabled = false;
                    btnSaveNN.textContent = 'Save NN Architecture';
                });
            });
        }
        
        // LLaMA Test
        var btnLLMTest = document.getElementById('btn-llm-test');
        if (btnLLMTest) {
            btnLLMTest.addEventListener('click', function() {
                btnLLMTest.disabled = true;
                btnLLMTest.textContent = 'Testing...';
                xhr('POST', '/api/llm/test', '', function(resp) {
                    var r = JSON.parse(resp);
                    var status = document.getElementById('llm-status');
                    if (r.ok) {
                        if (status) { status.textContent = 'Connected'; status.style.color = 'var(--neon-green)'; }
                        if (window.showToast) window.showToast('LLaMA ping OK: ' + (r.test_response || ''), 'success');
                    } else {
                        if (status) { status.textContent = 'Failed'; status.style.color = 'var(--neon-red)'; }
                        if (window.showToast) window.showToast('LLaMA test FAILED', 'error');
                    }
                    btnLLMTest.disabled = false;
                    btnLLMTest.textContent = 'Test Connection';
                });
            });
        }
        
        // Force Sentiment
        var btnSentiment = document.getElementById('btn-llm-sentiment-now');
        if (btnSentiment) {
            btnSentiment.addEventListener('click', function() {
                btnSentiment.disabled = true;
                btnSentiment.textContent = 'Analyzing...';
                xhr('POST', '/api/llm/sentiment', '', function(resp) {
                    var r = JSON.parse(resp);
                    var container = document.getElementById('llm-latest-analysis');
                    if (container && r.ok && r.sentiment) {
                        container.innerHTML = '<div style="padding: 8px; border-radius: 6px; background: rgba(0,240,255,0.03);"><strong>Sentiment:</strong> ' + 
                            (r.sentiment.direction || 'unknown').toUpperCase() + ' (score: ' + (r.sentiment.sentiment_score || 0).toFixed(2) + 
                            ')<br><small>' + (r.sentiment.analysis || '') + '</small></div>';
                    }
                    if (window.showToast) window.showToast('Sentiment: ' + (r.ok ? 'Done' : r.error), r.ok ? 'success' : 'error');
                    btnSentiment.disabled = false;
                    btnSentiment.textContent = 'Poll Sentiment Now';
                });
            });
        }
        
        // Force Regime
        var btnRegime = document.getElementById('btn-llm-regime-now');
        if (btnRegime) {
            btnRegime.addEventListener('click', function() {
                btnRegime.disabled = true;
                btnRegime.textContent = 'Classifying...';
                xhr('POST', '/api/llm/regime', '', function(resp) {
                    var r = JSON.parse(resp);
                    var container = document.getElementById('llm-latest-analysis');
                    if (container && r.ok && r.regime) {
                        var h = '<div style="padding: 8px; border-radius: 6px; background: rgba(168,85,247,0.03);"><strong>Regime:</strong> ' + 
                            (r.regime.regime || 'unknown').toUpperCase() + ' (' + ((r.regime.confidence||0)*100).toFixed(0) + '% confidence)';
                        if (r.regime.analysis) h += '<br><small>' + r.regime.analysis + '</small>';
                        h += '</div>';
                        container.innerHTML = (container.innerHTML || '') + h;
                    }
                    if (window.showToast) window.showToast('Regime: ' + (r.ok ? 'Done' : r.error), r.ok ? 'success' : 'error');
                    btnRegime.disabled = false;
                    btnRegime.textContent = 'Classify Regime';
                });
            });
        }
        
        // Save LLM Config
        var btnSaveLLM = document.getElementById('btn-save-llm-config');
        if (btnSaveLLM) {
            btnSaveLLM.addEventListener('click', function() {
                var config = {};
                var e = document.getElementById('llm-config-endpoint');
                var i = document.getElementById('llm-config-interval');
                var t = document.getElementById('llm-config-timeout');
                var en = document.getElementById('llm-config-enabled');
                if (e) config.endpoint = e.value;
                if (i) config.poll_interval_sec = parseInt(i.value) || 900;
                if (t) config.timeout_sec = parseInt(t.value) || 60;
                if (en) config.enabled = en.checked;
                
                btnSaveLLM.disabled = true;
                btnSaveLLM.textContent = 'Saving...';
                xhr('POST', '/api/llm/config', JSON.stringify(config), function(resp) {
                    var r = JSON.parse(resp);
                    var status = document.getElementById('llm-config-status');
                    if (r.ok) {
                        if (status) { status.textContent = 'Saved: ' + r.changes.join(', '); status.style.color = 'var(--neon-green)'; }
                        if (window.showToast) window.showToast('LLM config saved', 'success');
                    } else {
                        if (status) { status.textContent = 'Error: ' + (r.error || 'unknown'); status.style.color = 'var(--neon-red)'; }
                    }
                    btnSaveLLM.disabled = false;
                    btnSaveLLM.textContent = 'Save Config';
                });
            });
        }
        
        // NN Tests
        var btnNNTests = document.getElementById('btn-run-nn-tests');
        if (btnNNTests) {
            btnNNTests.addEventListener('click', function() {
                var results = document.getElementById('nn-test-results');
                btnNNTests.disabled = true;
                btnNNTests.textContent = 'Running...';
                if (results) results.textContent = 'Running...';
                xhr('POST', '/api/nn/tests', '', function(resp) {
                    var r = JSON.parse(resp);
                    btnNNTests.disabled = false;
                    btnNNTests.textContent = 'Run NN Tests';
                    if (results) {
                        results.innerHTML = '<pre style="margin:0; font-size:10px;">Passed: ' + (r.passed||0) + ' | Failed: ' + (r.failed||0) + '\n' + (r.output||'').substring(0,500) + '</pre>';
                    }
                    if (window.showToast) window.showToast('Tests: ' + (r.ok ? (r.passed||0)+' passed' : (r.failed||0)+' failed'), r.ok ? 'success' : 'error');
                });
            });
        }
        
        // Training triggers
        var btnTrain = document.getElementById('btn-trigger-training');
        if (btnTrain) {
            btnTrain.addEventListener('click', function() {
                var s = document.getElementById('training-status');
                btnTrain.disabled = true;
                btnTrain.textContent = 'Starting...';
                if (s) s.textContent = 'Starting...';
                xhr('POST', '/api/training/run', JSON.stringify({days:30,epochs:20}), function(resp) {
                    var r = JSON.parse(resp);
                    btnTrain.disabled = false;
                    btnTrain.textContent = 'Train with Last 30 Days';
                    if (s) { s.textContent = r.message || r.error; s.style.color = r.ok ? 'var(--neon-green)' : 'var(--neon-red)'; }
                    if (window.showToast) window.showToast(r.ok ? 'Training started' : 'Error: '+r.error, r.ok?'success':'error');
                });
            });
        }
        
        var btnHistorical = document.getElementById('btn-run-historical-pipeline');
        if (btnHistorical) {
            btnHistorical.addEventListener('click', function() {
                var s = document.getElementById('training-status');
                btnHistorical.disabled = true;
                btnHistorical.textContent = 'Running...';
                if (s) s.textContent = 'Fetching data...';
                xhr('POST', '/api/training/run', JSON.stringify({days:90,epochs:30}), function(resp) {
                    var r = JSON.parse(resp);
                    btnHistorical.disabled = false;
                    btnHistorical.textContent = 'Run 90-Day Full Pipeline';
                    if (s) { s.textContent = r.message || r.error; s.style.color = r.ok ? 'var(--neon-green)' : 'var(--neon-red)'; }
                    if (window.showToast) window.showToast(r.ok ? 'Pipeline started' : 'Error: '+r.error, r.ok?'success':'error');
                });
            });
        }

        // Init LLM tab when navigated to
        var llmNavBtn = document.querySelector('[data-tab="tab-llm"]');
        if (llmNavBtn) {
            llmNavBtn.addEventListener('click', function() {
                setTimeout(initLLMTab, 300);
            });
        }
        
        setTimeout(initLLMTab, 3000);


})();
