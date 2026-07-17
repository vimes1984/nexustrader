// App.js for NexusTrader Dashboard
let socket = null;
let chart = null;

// Chart state
const maxChartPoints = 40;
const chartLabels = [];
const priceData = [];
const rsiData = [];
const bbUpperData = [];
const bbLowerData = [];
const ema12Data = [];
const ema26Data = [];

// App State
let activeTicker = "ETH-EUR";
const tickerLatest = {};
let activePosition = null;
let currentPrice = 0.0;
let balance = 100.0;
let equity = 100.0;
let initialBalance = 100.0;
let totalClosedPnL = 0.0;
let isStopped = false;
let currentWeights = {};

// Colors mapping for strategies
const strategyColors = {
    "EMA Crossover": "#00f0ff",
    "RSI Reversion": "#38bdf8",
    "BB Breakout": "#a855f7",
    "ML Random Forest": "#f43f5e",
    "Kalman Filter Trend": "#10b981",
    "Psych Liquidity Sweep": "#f59e0b"
};

// DOM elements
const elPrice = document.getElementById("ticker-price");
const elEquity = document.getElementById("val-equity");
const elUnrealized = document.getElementById("val-unrealized-pnl");
const elBalance = document.getElementById("val-balance");
const elWinrate = document.getElementById("val-winrate");
const elTradeCount = document.getElementById("val-trade-count");
const elTotalPnL = document.getElementById("val-total-pnl");
const elTotalPnLPercent = document.getElementById("val-total-pnl-percent");
const elWeightsContainer = document.getElementById("weights-container");
const elPositionDetails = document.getElementById("position-details-container");
const elTradeLogBody = document.getElementById("trade-log-body");
const elProbGauge = document.getElementById("prob-gauge");
const elProbValue = document.getElementById("prob-value");
const elValEv = document.getElementById("val-ev");
const elValRr = document.getElementById("val-rr");
const elValKelly = document.getElementById("val-kelly");
const elValSigStrength = document.getElementById("val-sig-strength");
const elViabilityBadge = document.getElementById("viability-badge");
const elPlayPauseBtn = document.getElementById("play-pause-btn");
const elPlayPauseText = document.getElementById("play-pause-text");
const elSpeedSlider = document.getElementById("speed-slider");
const elSpeedLabel = document.getElementById("speed-label");
const elResetBtn = document.getElementById("reset-btn");
const elRiskSelect = document.getElementById("risk-mode-select");

// Initialize Chart
function initChart() {
    const ctx = document.getElementById('main-chart').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [
                {
                    label: 'Close Price',
                    data: priceData,
                    borderColor: '#00f0ff',
                    borderWidth: 2,
                    tension: 0.15,
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'BB Upper',
                    data: bbUpperData,
                    borderColor: 'rgba(168, 85, 247, 0.3)',
                    borderWidth: 1,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'BB Lower',
                    data: bbLowerData,
                    borderColor: 'rgba(168, 85, 247, 0.3)',
                    borderWidth: 1,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#94a3b8',
                        font: {
                            family: 'Space Grotesk',
                            size: 11
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.03)'
                    },
                    ticks: {
                        color: '#64748b',
                        maxTicksLimit: 6
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.03)'
                    },
                    ticks: {
                        color: '#64748b'
                    }
                }
            }
        }
    });
}

// Connect WebSocket
function connectWebSocket() {
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProto}//${window.location.host}/ws`;
    
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("WebSocket connected.");
        document.getElementById("bot-status").classList.remove("stopped");
    };

    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleSocketMessage(msg);
    };

    socket.onclose = () => {
        console.log("WebSocket disconnected. Retrying in 3s...");
        document.getElementById("status-text").textContent = "Disconnected";
        document.getElementById("bot-status").classList.add("stopped");
        setTimeout(connectWebSocket, 3000);
    };

    socket.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

// Message Router
function handleSocketMessage(msg) {
    switch (msg.type) {
        case "init":
            handleInitState(msg);
            break;
        case "tick":
            handleTick(msg);
            break;
        case "trade_opened":
            handleTradeOpened(msg);
            break;
        case "trade_closed":
            handleTradeClosed(msg);
            break;
        case "learning_update":
            handleLearningUpdate(msg);
            break;
        case "risk_mode_updated":
            if (elRiskSelect) elRiskSelect.value = msg.risk_mode;
            break;
    }
}

// Process Init Message
function handleInitState(data) {
    balance = data.balance;
    equity = data.equity !== undefined ? data.equity : data.balance;
    if (data.initial_balance !== undefined) {
        initialBalance = data.initial_balance;
    }
    
    // Set active ticker default if not set
    if (data.ticker && !activeTicker) {
        activeTicker = data.ticker;
    }
    document.getElementById("chart-ticker-title").textContent = activeTicker;
    
    // Render Ticker Switcher tabs
    const switcherEl = document.getElementById("ticker-switcher-bar");
    if (switcherEl && data.tickers) {
        switcherEl.innerHTML = "";
        data.tickers.forEach(t => {
            const btn = document.createElement("button");
            btn.className = `ticker-tab ${t === activeTicker ? 'active' : ''}`;
            btn.id = `tab-${t}`;
            btn.setAttribute("data-ticker", t);
            btn.innerHTML = `
                <span class="ticker-tab-name">${t}</span>
                <span class="ticker-tab-price" id="tab-price-${t}">€0.00</span>
            `;
            btn.addEventListener("click", () => switchTicker(t));
            switcherEl.appendChild(btn);
        });
    }

    // Toggle controls and status badges based on trading mode (live vs paper)
    const tradingMode = data.trading_mode || "paper";
    const brokerName = data.broker || "kraken";
    const statusTextEl = document.getElementById("status-text");
    const botStatusEl = document.getElementById("bot-status");
    const speedEl = document.getElementById("speed-slider") ? document.getElementById("speed-slider").parentElement : null;
    const playPauseBtn = document.getElementById("play-pause-btn");
    const resetBtn = document.getElementById("reset-btn");
    
    if (tradingMode === "live") {
        if (statusTextEl) statusTextEl.textContent = `Live (${brokerName.toUpperCase()})`;
        if (botStatusEl) {
            botStatusEl.className = "status-badge live";
        }
        if (speedEl) speedEl.style.display = "none";
        if (playPauseBtn) playPauseBtn.style.display = "none";
        if (resetBtn) resetBtn.style.display = "none";
    } else {
        if (statusTextEl) statusTextEl.textContent = "Simulating";
        if (botStatusEl) {
            botStatusEl.className = "status-badge";
        }
        if (speedEl) speedEl.style.display = "flex";
        if (playPauseBtn) playPauseBtn.style.display = "flex";
        if (resetBtn) resetBtn.style.display = "flex";
    }
    
    currentWeights = data.weights;
    renderWeights(currentWeights);
    renderTradeLog(data.trades);
    updatePerformanceKPIs(data.trades, equity);
    
    // Switch to active ticker history initial loading
    fetch(`/api/history?ticker=${activeTicker}&t=${Date.now()}`)
        .then(res => res.json())
        .then(history => {
            if (Array.isArray(history) && history.length > 0) {
                chartLabels.length = 0;
                priceData.length = 0;
                bbUpperData.length = 0;
                bbLowerData.length = 0;
                history.forEach(item => {
                    const timeLabel = item.timestamp.split(" ")[1] || item.timestamp.split("T")[1]?.slice(0, 5) || item.timestamp;
                    chartLabels.push(timeLabel);
                    priceData.push(item.close);
                    bbUpperData.push(item.bb_upper);
                    bbLowerData.push(item.bb_lower);
                });
                chart.update();
            }
        });
    
    if (data.risk_mode && elRiskSelect) {
        elRiskSelect.value = data.risk_mode;
    }
}

// Process Tick Message
function handleTick(data) {
    // Store latest tick for this symbol
    tickerLatest[data.ticker] = data;
    
    // Update ticker price shown on switcher tab
    const tabPriceEl = document.getElementById(`tab-price-${data.ticker}`);
    if (tabPriceEl) {
        tabPriceEl.textContent = `€${data.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }
    
    // If this tick belongs to another ticker, do not update the main chart or details cards
    if (data.ticker !== activeTicker) {
        return;
    }
    
    currentPrice = data.price;
    elPrice.textContent = `€${currentPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Update balance & equity card
    balance = data.balance;
    equity = data.equity !== undefined ? data.equity : data.balance;
    elBalance.textContent = `€${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elEquity.textContent = `€${equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Update unrealized calculations
    activePosition = data.position;
    if (activePosition) {
        const entry = activePosition.entry_price;
        const qty = activePosition.quantity;
        const direction = activePosition.direction;
        let unrealizedDollar = 0;
        
        if (direction === "BUY") {
            unrealizedDollar = (currentPrice - entry) * qty;
        } else {
            unrealizedDollar = (entry - currentPrice) * qty;
        }
        
        const cost = entry * qty;
        const unrealizedPercent = (unrealizedDollar / cost) * 100;
        
        elUnrealized.textContent = `Active Trade Profit: ${unrealizedDollar >= 0 ? '+' : ''}€${unrealizedDollar.toFixed(2)} (${unrealizedPercent.toFixed(2)}%)`;
        elUnrealized.className = unrealizedDollar >= 0 ? "kpi-sub color-green" : "kpi-sub color-red";
        
        renderActivePosition(activePosition, unrealizedDollar, unrealizedPercent);
    } else {
        elUnrealized.textContent = `Active Trade Profit: €0.00 (0.00%)`;
        elUnrealized.className = "kpi-sub";
        elPositionDetails.innerHTML = `<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Trade Currently Open</p>`;
    }

    // Process evaluation odds
    if (data.evaluation) {
        updateEvaluationWidget(data.evaluation, data.weighted_signal);
    }

    // Push chart data
    const timeLabel = data.timestamp.split(" ")[1] || data.timestamp.split("T")[1]?.slice(0, 5) || data.timestamp;
    chartLabels.push(timeLabel);
    priceData.push(currentPrice);
    bbUpperData.push(data.indicators.bb_upper);
    bbLowerData.push(data.indicators.bb_lower);

    if (chartLabels.length > maxChartPoints) {
        chartLabels.shift();
        priceData.shift();
        bbUpperData.shift();
        bbLowerData.shift();
    }

    chart.update('none'); // Update without full recalculation transition for smooth updates

    // Update Neural State inputs if present in tick
    if (data.neural_state) {
        const state = data.neural_state;
        const is_mr = state[0];
        const theta = state[1];
        const rsi = state[2];
        const macd_norm = state[3];
        const bb_pos = state[4];
        const atr_ratio = state[5];
        const win_trend = state[6];
        
        const elRegime = document.getElementById("neural-val-regime");
        if (elRegime) {
            elRegime.textContent = is_mr === 1.0 ? "Mean Reverting" : "Trending";
            elRegime.style.color = is_mr === 1.0 ? "var(--neon-purple)" : "var(--neon-blue)";
        }
        
        const elTheta = document.getElementById("neural-val-theta");
        if (elTheta) elTheta.textContent = theta.toFixed(4);
        
        const elRsi = document.getElementById("neural-val-rsi");
        if (elRsi) elRsi.textContent = rsi.toFixed(4);
        
        const elMacd = document.getElementById("neural-val-macd");
        if (elMacd) elMacd.textContent = macd_norm.toFixed(4);
        
        const elBb = document.getElementById("neural-val-bb");
        if (elBb) elBb.textContent = bb_pos.toFixed(4);
        
        const elAtr = document.getElementById("neural-val-atr");
        if (elAtr) elAtr.textContent = atr_ratio.toFixed(4);
        
        const elWinTrend = document.getElementById("neural-val-wintrend");
        if (elWinTrend) elWinTrend.textContent = `${(win_trend * 100).toFixed(1)}%`;
    }
}

// Switch Active Ticker Handler
function switchTicker(ticker) {
    if (ticker === activeTicker) return;
    activeTicker = ticker;
    
    // Update tab classes
    document.querySelectorAll(".ticker-tab").forEach(tab => {
        if (tab.getAttribute("data-ticker") === ticker) {
            tab.classList.add("active");
        } else {
            tab.classList.remove("active");
        }
    });
    
    document.getElementById("chart-ticker-title").textContent = ticker;
    
    // Clear chart datasets
    chartLabels.length = 0;
    priceData.length = 0;
    bbUpperData.length = 0;
    bbLowerData.length = 0;
    
    // Fetch historical candles for this ticker
    fetch(`/api/history?ticker=${ticker}&t=${Date.now()}`)
        .then(res => res.json())
        .then(history => {
            if (Array.isArray(history) && history.length > 0) {
                history.forEach(item => {
                    const timeLabel = item.timestamp.split(" ")[1] || item.timestamp.split("T")[1]?.slice(0, 5) || item.timestamp;
                    chartLabels.push(timeLabel);
                    priceData.push(item.close);
                    bbUpperData.push(item.bb_upper);
                    bbLowerData.push(item.bb_lower);
                });
                chart.update();
            }
        })
        .catch(err => console.error("Error loading historical candles:", err));
        
    // Fetch weights for this ticker
    fetch(`/api/weights?ticker=${ticker}&t=${Date.now()}`)
        .then(res => res.json())
        .then(weights => {
            currentWeights = weights;
            renderWeights(currentWeights);
        })
        .catch(err => console.error("Error loading weights:", err));
        
    // Update active position/evaluation display for the new ticker from latest socket tick
    const tick = tickerLatest[ticker];
    if (tick) {
        handleTick(tick);
    } else {
        elPrice.textContent = "€0.00";
        elUnrealized.textContent = "Active Trade Profit: €0.00 (0.00%)";
        elUnrealized.className = "kpi-sub";
        elPositionDetails.innerHTML = `<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Trade Currently Open</p>`;
    }
}

function handleTradeOpened(data) {
    activePosition = data.position;
    balance = data.balance;
    equity = data.equity !== undefined ? data.equity : data.balance;
    elBalance.textContent = `€${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elEquity.textContent = `€${equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Pulse card glow
    const card = document.getElementById("equity-card");
    card.classList.add("active");
    setTimeout(() => card.classList.remove("active"), 1000);
}

function handleTradeClosed(data) {
    activePosition = null;
    balance = data.balance;
    equity = data.equity !== undefined ? data.equity : data.balance;
    elBalance.textContent = `€${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elEquity.textContent = `€${equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Add trade to execution log and update stats
    renderTradeClosedState(data.trade);
}

function handleLearningUpdate(data) {
    currentWeights = data.weights;
    renderWeights(currentWeights);
    
    // Log weight update in diagnostics panel
    const logBox = document.getElementById("neural-log");
    if (logBox) {
        const timeStr = new Date().toLocaleTimeString();
        const pnl = data.pnl ? (data.pnl * 100).toFixed(2) + "%" : "0.00%";
        const pnlColor = data.pnl >= 0 ? "var(--neon-green)" : "var(--neon-red)";
        
        const entry = document.createElement("div");
        entry.style.marginBottom = "6px";
        entry.style.borderBottom = "1px solid rgba(255,255,255,0.02)";
        entry.style.paddingBottom = "4px";
        entry.innerHTML = `<span style="color:var(--text-muted)">[${timeStr}]</span> <span style="font-weight:600;color:var(--neon-blue)">${data.ticker}</span> weights updated (Reward: <span style="color:${pnlColor};font-weight:600;">${pnl}</span>)`;
        
        if (logBox.textContent.trim().startsWith("Waiting")) {
            logBox.innerHTML = "";
        }
        
        logBox.insertBefore(entry, logBox.firstChild);
    }
}

// UI Render Helpers
function renderWeights(weights) {
    elWeightsContainer.innerHTML = "";
    Object.keys(weights).forEach(name => {
        const wt = weights[name];
        const percent = (wt * 100).toFixed(1);
        const color = strategyColors[name] || "#ffffff";
        
        const row = document.createElement("div");
        row.className = "weight-row";
        row.innerHTML = `
            <div class="weight-labels">
                <span>${name}</span>
                <span style="font-weight: 600; color: ${color}">${percent}%</span>
            </div>
            <div class="weight-bar-bg">
                <div class="weight-bar-fill" style="width: ${percent}%; background: ${color};"></div>
            </div>
        `;
        elWeightsContainer.appendChild(row);
    });
}

function renderActivePosition(pos, unrlDollar, unrlPct) {
    const isProfit = unrlDollar >= 0;
    const directionColor = pos.direction === "BUY" ? "var(--neon-green)" : "var(--neon-red)";
    const buySellLabel = pos.direction === "BUY" ? "BUY (Upward Trend)" : "SELL (Downward Trend)";
    
    elPositionDetails.innerHTML = `
        <div class="pos-row">
            <span>Buy / Sell</span>
            <span style="font-weight:600; color: ${directionColor};">${buySellLabel}</span>
        </div>
        <div class="pos-row">
            <span>Shares Invested</span>
            <span>${pos.quantity.toFixed(4)}</span>
        </div>
        <div class="pos-row">
            <span>Entry Price</span>
            <span>€${pos.entry_price.toFixed(2)}</span>
        </div>
        <div class="pos-row">
            <span>Profit Target</span>
            <span class="color-green">€${pos.take_profit.toFixed(2)}</span>
        </div>
        <div class="pos-row">
            <span>Max Loss Limit</span>
            <span class="color-red">€${pos.stop_loss.toFixed(2)}</span>
        </div>
        <div class="pos-row" style="background: rgba(255,255,255,0.05); font-weight:600;">
            <span>Current Profit</span>
            <span class="${isProfit ? 'color-green' : 'color-red'}">${isProfit ? '+' : ''}€${unrlDollar.toFixed(2)} (${unrlPct.toFixed(2)}%)</span>
        </div>
    `;
}

function updateEvaluationWidget(eval, signal) {
    const winProbPct = Math.round(eval.win_probability * 100);
    elProbGauge.style.setProperty("--gauge-percent", `${(winProbPct / 100) * 360}deg`);
    elProbValue.textContent = `${winProbPct}%`;
    
    elValEv.textContent = `${eval.expected_value >= 0 ? '+' : ''}€${eval.expected_value.toFixed(2)}`;
    elValEv.className = eval.expected_value >= 0 ? "color-green" : "color-red";
    
    elValRr.textContent = `1 : ${eval.risk_reward_ratio.toFixed(1)}`;
    elValKelly.textContent = `${(eval.kelly_fraction * 100).toFixed(1)}%`;
    elValSigStrength.textContent = `${Math.abs(signal * 100).toFixed(0)}%`;
    
    if (eval.is_viable) {
        elViabilityBadge.textContent = "YES - Highly viable trade setup";
        elViabilityBadge.style.background = "rgba(16, 185, 129, 0.1)";
        elViabilityBadge.style.border = "1px solid var(--neon-green)";
        elViabilityBadge.style.color = "var(--neon-green)";
    } else {
        elViabilityBadge.textContent = "NO - Safe to stand aside";
        elViabilityBadge.style.background = "rgba(244, 63, 94, 0.05)";
        elViabilityBadge.style.border = "1px solid rgba(244, 63, 94, 0.2)";
        elViabilityBadge.style.color = "var(--text-muted)";
    }
}

function renderTradeLog(trades) {
    if (!trades || trades.length === 0) {
        elTradeLogBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 40px;">No trades completed yet. Watching the market for opportunities...</td></tr>`;
        return;
    }
    
    elTradeLogBody.innerHTML = "";
    
    // Render in reverse chronological order (newest first)
    [...trades].reverse().forEach(t => {
        const timeStr = new Date(t.exit_time * 1000).toLocaleTimeString();
        const pnlColor = t.pnl >= 0 ? "color-green" : "color-red";
        const sign = t.pnl >= 0 ? "+" : "";
        const outcomeBadge = t.pnl >= 0 ? "PROFIT" : "LOSS";
        const outcomeColor = t.pnl >= 0 ? "rgba(16, 185, 129, 0.15)" : "rgba(244, 63, 94, 0.15)";
        
        // Sum the weights of strategies that had a matching signal at entry
        // (Visual reference to show which strategies contributed to trade success)
        
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${timeStr}</td>
            <td>${t.symbol}</td>
            <td style="color: ${t.direction === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)'}; font-weight:600;">${t.direction}</td>
            <td>${t.quantity.toFixed(4)}</td>
            <td>€${t.entry_price.toFixed(2)}</td>
            <td>€${t.exit_price.toFixed(2)}</td>
            <td>72%</td> <!-- Estimated base -->
            <td class="${pnlColor}" style="font-weight:600;">${sign}€${t.pnl.toFixed(2)} (${(t.pnl_percent*100).toFixed(2)}%)</td>
            <td><span style="background: ${outcomeColor}; color: ${t.pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'}; padding: 4px 8px; border-radius: 4px; font-size:11px; font-weight:600;">${t.exit_reason.toUpperCase()}</span></td>
        `;
        elTradeLogBody.appendChild(row);
    });
}

function renderTradeClosedState(closedTrade) {
    // Re-fetch all trades and update statistics
    fetch(`/api/trades?t=${Date.now()}`)
        .then(res => res.json())
        .then(trades => {
            renderTradeLog(trades);
            updatePerformanceKPIs(trades, equity);
        });
}

function updatePerformanceKPIs(trades, currentEquity) {
    if (!trades || trades.length === 0) {
        elWinrate.textContent = "0.0%";
        elTradeCount.textContent = "0 trades completed";
        elTotalPnL.textContent = "€0.00";
        elTotalPnLPercent.textContent = "0.00% growth";
        elTotalPnL.className = "kpi-value";
        elTotalPnLPercent.className = "kpi-sub";
        return;
    }
    
    const winCount = trades.filter(t => t.pnl > 0).length;
    const wr = (winCount / trades.length) * 100;
    elWinrate.textContent = `${wr.toFixed(1)}%`;
    elTradeCount.textContent = `${trades.length} trades completed`;
    
    // Net profit
    const netPnL = currentEquity - initialBalance;
    const netPct = (netPnL / initialBalance) * 100;
    
    elTotalPnL.textContent = `${netPnL >= 0 ? '+' : ''}€${netPnL.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elTotalPnLPercent.textContent = `${netPnL >= 0 ? '+' : ''}${netPct.toFixed(2)}% growth`;
    
    elTotalPnL.className = netPnL >= 0 ? "kpi-value color-green" : "kpi-value color-red";
    elTotalPnLPercent.className = netPnL >= 0 ? "kpi-sub color-green" : "kpi-sub color-red";
}

// User Interaction Listeners
elPlayPauseBtn.addEventListener("click", () => {
    isStopped = !isStopped;
    const action = isStopped ? "stop" : "start";
    const speed = parseFloat(elSpeedSlider.value);
    
    fetch(`/api/control?action=${action}&speed=${speed}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (isStopped) {
                elPlayPauseText.textContent = "Resume";
                elPlayPauseBtn.querySelector("i").setAttribute("data-lucide", "play");
                document.getElementById("status-text").textContent = "Paused";
                document.getElementById("bot-status").classList.add("stopped");
            } else {
                elPlayPauseText.textContent = "Pause";
                elPlayPauseBtn.querySelector("i").setAttribute("data-lucide", "pause");
                document.getElementById("status-text").textContent = "Simulating";
                document.getElementById("bot-status").classList.remove("stopped");
            }
            lucide.createIcons();
        });
});

elSpeedSlider.addEventListener("input", (e) => {
    const val = parseFloat(e.target.value);
    elSpeedLabel.textContent = `${val.toFixed(2)}s`;
    
    if (!isStopped) {
        // Update speed on the fly
        fetch(`/api/control?action=start&speed=${val}`, { method: 'POST' });
    }
});

elResetBtn.addEventListener("click", () => {
    if (confirm("Are you sure you want to reset simulation, balance, and learning weights?")) {
        fetch("/api/control?action=reset", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                // Reset local states
                priceData.length = 0;
                chartLabels.length = 0;
                bbUpperData.length = 0;
                bbLowerData.length = 0;
                chart.update();
                
                isStopped = false;
                elPlayPauseText.textContent = "Pause";
                elPlayPauseBtn.querySelector("i").setAttribute("data-lucide", "pause");
                document.getElementById("status-text").textContent = "Simulating";
                document.getElementById("bot-status").classList.remove("stopped");
                lucide.createIcons();
                
                // Re-establish stats
                balance = 100.0;
                elBalance.textContent = "€100.00";
                elEquity.textContent = "€100.00";
                elUnrealized.textContent = "Active Trade Profit: €0.00 (0.00%)";
                elUnrealized.className = "kpi-sub";
                
                // Reset the DOM trades log table
                elTradeLogBody.innerHTML = `
                    <tr>
                        <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 40px;">No trades completed yet. Watching the market for opportunities...</td>
                    </tr>
                `;
                
                // Reset active position container
                elPositionDetails.innerHTML = `<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Trade Currently Open</p>`;
                
                // Reset the performance KPI cards
                updatePerformanceKPIs([], 100.0);
                
                // Clear the Neural Diagnostics update log
                const logBox = document.getElementById("neural-log");
                if (logBox) logBox.innerHTML = "Waiting for training updates...";
                
                console.log("Simulation reset successfully.");
            });
    }
});

// Risk Mode Event Listener
if (elRiskSelect) {
    elRiskSelect.addEventListener("change", (e) => {
        const val = e.target.value;
        fetch(`/api/system/risk_mode?risk_mode=${val}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                console.log(`Risk profile updated to: ${data.risk_mode}`);
            });
    });
}

// Blog & System Configuration Controls
const elBlogEnabledCheck = document.getElementById("blog-enabled-check");
const elBlogGitPushCheck = document.getElementById("blog-git-push-check");
const elBlogAiCheck = document.getElementById("blog-ai-check");
const elBlogApiKey = document.getElementById("blog-api-key");
const elSaveBlogConfigBtn = document.getElementById("save-blog-config-btn");
const elTriggerBlogBtn = document.getElementById("trigger-blog-btn");
const elBlogStatusMsg = document.getElementById("blog-status-msg");

const elTradingModeSelect = document.getElementById("setting-trading-mode");
const elBrokerSelect = document.getElementById("setting-broker");
const elApiKeyInput = document.getElementById("setting-api-key");
const elApiSecretInput = document.getElementById("setting-api-secret");
const elTrailingStopCheck = document.getElementById("setting-trailing-stop");
const elCooldownInput = document.getElementById("setting-cooldown");
const elMaxDrawdownInput = document.getElementById("setting-max-drawdown");
const elTpMultiplierInput = document.getElementById("setting-tp-multiplier");
const elSlMultiplierInput = document.getElementById("setting-sl-multiplier");

function loadBlogConfig() {
    // 1. Fetch Blog configurations
    fetch(`/api/blog/config?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            if (elBlogEnabledCheck) elBlogEnabledCheck.checked = data.blog_enabled;
            if (elBlogGitPushCheck) elBlogGitPushCheck.checked = data.blog_git_push_enabled;
            if (elBlogAiCheck) elBlogAiCheck.checked = data.blog_ai_enabled;
            if (elBlogApiKey) elBlogApiKey.value = data.blog_gemini_api_key || "";
        })
        .catch(err => console.error("Error loading blog config:", err));

    // 2. Fetch System configurations
    fetch(`/api/system/config?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            if (elTradingModeSelect) elTradingModeSelect.value = data.trading_mode || "paper";
            if (elBrokerSelect) elBrokerSelect.value = data.broker || "kraken";
            if (elApiKeyInput) elApiKeyInput.value = data.api_key || "";
            if (elApiSecretInput) elApiSecretInput.value = data.api_secret || "";
            if (elTrailingStopCheck) elTrailingStopCheck.checked = data.trailing_stop || false;
            if (elCooldownInput) elCooldownInput.value = data.cooldown || 4;
            if (elMaxDrawdownInput) elMaxDrawdownInput.value = data.max_drawdown || 5;
            if (elTpMultiplierInput) elTpMultiplierInput.value = data.tp_multiplier || 2.5;
            if (elSlMultiplierInput) elSlMultiplierInput.value = data.sl_multiplier || 1.5;
        })
        .catch(err => console.error("Error loading system config:", err));
}

if (elSaveBlogConfigBtn) {
    elSaveBlogConfigBtn.addEventListener("click", () => {
        const enabled = elBlogEnabledCheck ? elBlogEnabledCheck.checked : true;
        const gitPush = elBlogGitPushCheck ? elBlogGitPushCheck.checked : true;
        const aiEnabled = elBlogAiCheck ? elBlogAiCheck.checked : false;
        const apiKey = elBlogApiKey ? elBlogApiKey.value.trim() : "";
        
        const tradingMode = elTradingModeSelect ? elTradingModeSelect.value : "paper";
        const broker = elBrokerSelect ? elBrokerSelect.value : "kraken";
        const exchangeApiKey = elApiKeyInput ? elApiKeyInput.value.trim() : "";
        const exchangeApiSecret = elApiSecretInput ? elApiSecretInput.value.trim() : "";
        const trailingStop = elTrailingStopCheck ? elTrailingStopCheck.checked : false;
        const cooldown = elCooldownInput ? parseFloat(elCooldownInput.value) : 4.0;
        const tpMultiplier = elTpMultiplierInput ? parseFloat(elTpMultiplierInput.value) : 2.5;
        const slMultiplier = elSlMultiplierInput ? parseFloat(elSlMultiplierInput.value) : 1.5;
        
        const riskMode = elRiskSelect ? elRiskSelect.value : "conservative";
        const maxDrawdown = elMaxDrawdownInput ? parseFloat(elMaxDrawdownInput.value) : 5.0;
        
        elBlogStatusMsg.textContent = "Saving settings...";
        elBlogStatusMsg.className = "color-blue";
        
        // 1. Save Blog settings
        const saveBlogPromise = fetch(`/api/blog/config?enabled=${enabled}&ai_enabled=${aiEnabled}&api_key=${encodeURIComponent(apiKey)}&git_push_enabled=${gitPush}`, {
            method: 'POST'
        });
        
        // 2. Save System settings
        const saveSystemPromise = fetch(`/api/system/config?trading_mode=${tradingMode}&risk_mode=${riskMode}&max_drawdown=${maxDrawdown}&broker=${broker}&api_key=${encodeURIComponent(exchangeApiKey)}&api_secret=${encodeURIComponent(exchangeApiSecret)}&trailing_stop=${trailingStop}&cooldown=${cooldown}&tp_multiplier=${tpMultiplier}&sl_multiplier=${slMultiplier}`, {
            method: 'POST'
        });

        Promise.all([saveBlogPromise, saveSystemPromise])
        .then(results => Promise.all(results.map(r => r.json())))
        .then(data => {
            elBlogStatusMsg.textContent = "Settings saved successfully!";
            elBlogStatusMsg.className = "color-green";
            setTimeout(() => { elBlogStatusMsg.textContent = ""; }, 3000);
        })
        .catch(err => {
            elBlogStatusMsg.textContent = "Error saving configuration.";
            elBlogStatusMsg.className = "color-red";
            console.error(err);
        });
    });
}

if (elTriggerBlogBtn) {
    elTriggerBlogBtn.addEventListener("click", () => {
        elBlogStatusMsg.textContent = "Generating blog post & syncing...";
        elBlogStatusMsg.className = "color-blue";
        elTriggerBlogBtn.disabled = true;
        
        // Confirm mock options
        const useMock = confirm("Do you want to generate mock trading data before blogging? (Cancel to generate with actual DB data)");
        
        fetch(`/api/blog/generate?use_mock=${useMock}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elTriggerBlogBtn.disabled = false;
                if (data.status === "success") {
                    elBlogStatusMsg.textContent = "Blog published successfully!";
                    elBlogStatusMsg.className = "color-green";
                    setTimeout(() => { elBlogStatusMsg.textContent = ""; }, 5000);
                    // Refresh trade log if mock was used
                    if (useMock) {
                        fetch(`/api/trades?t=${Date.now()}`)
                            .then(res => res.json())
                            .then(trades => {
                                renderTradeLog(trades);
                                updatePerformanceKPIs(trades, equity);
                            });
                    }
                } else {
                    elBlogStatusMsg.textContent = `Error: ${data.error || "failed"}`;
                    elBlogStatusMsg.className = "color-red";
                }
            })
            .catch(err => {
                elTriggerBlogBtn.disabled = false;
                elBlogStatusMsg.textContent = "Error generating blog.";
                elBlogStatusMsg.className = "color-red";
                console.error(err);
            });
    });
}

const elOptSentimentBtn = document.getElementById("trigger-opt-sentiment-btn");
const elOptParamsBtn = document.getElementById("trigger-opt-params-btn");

if (elOptSentimentBtn) {
    elOptSentimentBtn.addEventListener("click", () => {
        elBlogStatusMsg.textContent = "Optimizing sentiment source weights...";
        elBlogStatusMsg.className = "color-blue";
        elOptSentimentBtn.disabled = true;

        fetch("/api/system/optimize/sentiment", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elOptSentimentBtn.disabled = false;
                if (data.status === "success") {
                    elBlogStatusMsg.textContent = "Sentiment weights optimized!";
                    elBlogStatusMsg.className = "color-green";
                    alert("Sentiment source weights optimized successfully!\n\n" + data.log);
                    setTimeout(() => { elBlogStatusMsg.textContent = ""; }, 5000);
                } else {
                    elBlogStatusMsg.textContent = `Error: ${data.error || "failed"}`;
                    elBlogStatusMsg.className = "color-red";
                }
            })
            .catch(err => {
                elOptSentimentBtn.disabled = false;
                elBlogStatusMsg.textContent = "Error optimizing sentiment.";
                elBlogStatusMsg.className = "color-red";
                console.error(err);
            });
    });
}

if (elOptParamsBtn) {
    elOptParamsBtn.addEventListener("click", () => {
        elBlogStatusMsg.textContent = "Running backtest hyperparameter optimization...";
        elBlogStatusMsg.className = "color-blue";
        elOptParamsBtn.disabled = true;

        fetch("/api/system/optimize/parameters", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elOptParamsBtn.disabled = false;
                if (data.status === "success") {
                    elBlogStatusMsg.textContent = "Parameters optimized!";
                    elBlogStatusMsg.className = "color-green";
                    alert("Hyperparameters optimized successfully!\n\n" + data.log);
                    setTimeout(() => { elBlogStatusMsg.textContent = ""; }, 5000);
                } else {
                    elBlogStatusMsg.textContent = `Error: ${data.error || "failed"}`;
                    elBlogStatusMsg.className = "color-red";
                }
            })
            .catch(err => {
                elOptParamsBtn.disabled = false;
                elBlogStatusMsg.textContent = "Error optimizing parameters.";
                elBlogStatusMsg.className = "color-red";
                console.error(err);
            });
    });
}

// 1. Test Broker API Connection Listener
const elTestBrokerBtn = document.getElementById("test-broker-api-btn");
if (elTestBrokerBtn) {
    elTestBrokerBtn.addEventListener("click", () => {
        elTestBrokerBtn.disabled = true;
        elBlogStatusMsg.textContent = "Testing broker API connection...";
        elBlogStatusMsg.className = "color-blue";
        
        fetch(`/api/system/test_broker?t=${Date.now()}`)
            .then(res => res.json())
            .then(data => {
                elTestBrokerBtn.disabled = false;
                if (data.status === "success") {
                    elBlogStatusMsg.textContent = data.message;
                    elBlogStatusMsg.className = "color-green";
                    
                    // Display balance info
                    const balStrings = Object.entries(data.balances).map(([asset, qty]) => `${qty} ${asset}`).join(", ");
                    alert(`✅ API Connection Success!\n\nBalances: ${balStrings || "No positive asset balances found."}`);
                    setTimeout(() => { elBlogStatusMsg.textContent = ""; }, 5000);
                } else {
                    elBlogStatusMsg.textContent = "Connection failed. Check details.";
                    elBlogStatusMsg.className = "color-red";
                    alert(`❌ API Connection Failed:\n\n${data.message}`);
                }
            })
            .catch(err => {
                elTestBrokerBtn.disabled = false;
                elBlogStatusMsg.textContent = "Error testing connection.";
                elBlogStatusMsg.className = "color-red";
                console.error(err);
            });
    });
}

// 2. Clear Loss Cooldowns Listener
const elResetCooldownsBtn = document.getElementById("trigger-reset-cooldowns-btn");
if (elResetCooldownsBtn) {
    elResetCooldownsBtn.addEventListener("click", () => {
        elResetCooldownsBtn.disabled = true;
        elBlogStatusMsg.textContent = "Clearing all loss cooldowns...";
        elBlogStatusMsg.className = "color-blue";
        
        fetch("/api/system/reset_cooldowns", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elResetCooldownsBtn.disabled = false;
                if (data.status === "success") {
                    elBlogStatusMsg.textContent = data.message;
                    elBlogStatusMsg.className = "color-green";
                    setTimeout(() => { elBlogStatusMsg.textContent = ""; }, 5000);
                } else {
                    elBlogStatusMsg.textContent = `Error: ${data.message || "failed"}`;
                    elBlogStatusMsg.className = "color-red";
                }
            })
            .catch(err => {
                elResetCooldownsBtn.disabled = false;
                elBlogStatusMsg.textContent = "Error resetting cooldowns.";
                elBlogStatusMsg.className = "color-red";
                console.error(err);
            });
    });
}

// App Startup
initChart();
connectWebSocket();
loadBlogConfig();
lucide.createIcons();

// Live Exchange holdings and open orders status polling
function updateExchangeStatus() {
    const elHoldingsContainer = document.getElementById("holdings-list-container");
    const elOpenOrdersContainer = document.getElementById("open-orders-list-container");
    
    if (!elHoldingsContainer || !elOpenOrdersContainer) return;
    
    fetch(`/api/exchange/status?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">${data.error}</p>`;
                elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Error loading orders.</p>`;
                return;
            }
            
            if (data.message) {
                elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">${data.message}</p>`;
                elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">${data.message}</p>`;
                return;
            }
            
            // Render holdings
            elHoldingsContainer.innerHTML = "";
            if (!data.holdings || data.holdings.length === 0) {
                elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">No holdings found.</p>`;
            } else {
                let totalEur = 0;
                data.holdings.forEach(h => {
                    totalEur += h.value_eur;
                    const row = document.createElement("div");
                    row.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 8px; font-size: 12px; transition: var(--transition);";
                    row.innerHTML = `
                        <span style="font-weight: 600; color: var(--text-primary);">${h.asset}</span>
                        <span style="color: var(--text-secondary); font-family: monospace;">${h.quantity.toFixed(4)}</span>
                        <span style="font-weight: 600; color: var(--neon-blue);">€${h.value_eur.toFixed(2)}</span>
                    `;
                    elHoldingsContainer.appendChild(row);
                });
                
                // Add Total row
                const totalRow = document.createElement("div");
                totalRow.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; margin-top: 6px; background: rgba(0, 240, 255, 0.04); border: 1px solid rgba(0, 240, 255, 0.15); border-radius: 8px; font-size: 12px; font-weight: 600;";
                totalRow.innerHTML = `
                    <span style="color: var(--text-primary);">Total Holdings Value</span>
                    <span style="color: var(--neon-blue); font-family: monospace;">€${totalEur.toFixed(2)}</span>
                `;
                elHoldingsContainer.appendChild(totalRow);
            }
            
            // Render Open Orders
            elOpenOrdersContainer.innerHTML = "";
            if (!data.open_orders || data.open_orders.length === 0) {
                elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">No pending orders found.</p>`;
            } else {
                data.open_orders.forEach(o => {
                    const row = document.createElement("div");
                    row.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 8px; font-size: 11px; transition: var(--transition);";
                    const sideColor = o.side === "buy" ? "var(--neon-green)" : "var(--neon-red)";
                    row.innerHTML = `
                        <div>
                            <span style="font-weight: 600; color: ${sideColor}; text-transform: uppercase;">${o.side}</span>
                            <span style="color: var(--text-primary); font-weight: 500;">${o.symbol}</span>
                        </div>
                        <span style="color: var(--text-secondary); font-family: monospace;">${o.amount} @ €${o.price}</span>
                    `;
                    elOpenOrdersContainer.appendChild(row);
                });
            }
        })
        .catch(err => {
            console.error("Error fetching exchange status:", err);
            elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Connection failed.</p>`;
            elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Connection failed.</p>`;
        });
}

// Initial pull and setup 15s interval
updateExchangeStatus();
setInterval(updateExchangeStatus, 15000);
