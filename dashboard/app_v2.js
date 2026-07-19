// App.js for NexusTrader Dashboard
let socket = null;
let chart = null;
let weightsChart = null;

// Notifications State
const notificationsList = JSON.parse(localStorage.getItem("nexustrader_alerts_history") || "[]");
let unreadCount = notificationsList.filter(n => !n.read).length;

// Cybernetic Floating Toast Notifications
function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    
    // Choose neon themes for the toast type
    let color = "var(--neon-blue)";
    let border = "1px solid rgba(0, 240, 255, 0.2)";
    let icon = "⚡";
    if (type === "success") {
        color = "var(--neon-green)";
        border = "1px solid rgba(16, 185, 129, 0.2)";
        icon = "✅";
    } else if (type === "error") {
        color = "var(--neon-red)";
        border = "1px solid rgba(244, 63, 94, 0.2)";
        icon = "❌";
    } else if (type === "info") {
        color = "var(--neon-purple)";
        border = "1px solid rgba(168, 85, 247, 0.2)";
        icon = "📡";
    }
    
    // Save notification to list
    const notification = {
        id: Date.now() + Math.random(),
        message: message,
        type: type,
        icon: icon,
        time: new Date().toLocaleTimeString(),
        read: false
    };
    notificationsList.unshift(notification);
    // Cap alerts list at 100 entries to prevent memory leak
    if (notificationsList.length > 100) {
        notificationsList.length = 100;
    }
    unreadCount++;
    localStorage.setItem("nexustrader_alerts_history", JSON.stringify(notificationsList));
    updateNotificationsUI();
    
    // Post notification to backend logs
    fetch('/api/system/log_notification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message, type: type })
    }).catch(err => console.warn("Failed to log notification to server: ", err));
    
    toast.style.background = "rgba(15, 23, 42, 0.9)";
    toast.style.color = "#ffffff";
    toast.style.borderLeft = `4px solid ${color}`;
    toast.style.borderTop = border;
    toast.style.borderRight = border;
    toast.style.borderBottom = border;
    toast.style.padding = "10px 16px";
    toast.style.borderRadius = "8px";
    toast.style.backdropFilter = "blur(12px)";
    toast.style.boxShadow = "0 8px 32px 0 rgba(0, 0, 0, 0.4)";
    toast.style.fontSize = "12px";
    toast.style.fontWeight = "600";
    toast.style.fontFamily = "'Space Grotesk', sans-serif";
    toast.style.display = "flex";
    toast.style.alignItems = "center";
    toast.style.gap = "10px";
    toast.style.cursor = "pointer";
    toast.style.pointerEvents = "auto";
    toast.style.opacity = "0";
    toast.style.transform = "translateY(20px)";
    toast.style.transition = "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)";
    toast.title = "Click to jump to relevant agent/section";
    
    toast.innerHTML = `<span style="font-size: 14px;">${icon}</span> <span style="flex-grow: 1;">${message}</span> <span style="font-size: 10px; opacity: 0.5;">${notification.time}</span>`;
    
    // Make popup clickable
    toast.addEventListener("click", () => {
        handleNotificationClick(notification);
        toast.remove();
    });
    
    container.appendChild(toast);
    
    // Animate in
    setTimeout(() => {
        toast.style.opacity = "1";
        toast.style.transform = "translateY(0)";
    }, 20);
    
    // Animate out and remove
    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(-15px)";
            setTimeout(() => {
                toast.remove();
            }, 300);
        }
    }, 4500);
}

// Function to handle notification navigation
function handleNotificationClick(notification) {
    notification.read = true;
    
    // Decrease unread count if applicable
    const dropdown = document.getElementById("notification-dropdown");
    if (dropdown && dropdown.style.display === "block") {
        notification.read = true;
    }
    
    const msgLower = notification.message.toLowerCase();
    let targetTab = null;
    let targetSelector = null;
    
    if (msgLower.includes("quant") || msgLower.includes("phd") || msgLower.includes("hyperparameter")) {
        targetTab = "tab-agents";
        targetSelector = "agent-quant-phd";
    } else if (msgLower.includes("dev") || msgLower.includes("architect") || msgLower.includes("codebase")) {
        targetTab = "tab-agents";
        targetSelector = "agent-dev-architect";
    } else if (msgLower.includes("blog") || msgLower.includes("weekly") || msgLower.includes("reporter")) {
        targetTab = "tab-agents";
        targetSelector = "agent-reporter";
    } else if (msgLower.includes("sentinel") || msgLower.includes("sentiment")) {
        targetTab = "tab-agents";
        targetSelector = "agent-sentiment-sentinel";
    } else if (msgLower.includes("risk") || msgLower.includes("audit") || msgLower.includes("drawdown")) {
        targetTab = "tab-agents";
        targetSelector = "agent-risk-auditor";
    } else if (msgLower.includes("neural") || msgLower.includes("nn") || msgLower.includes("tuning") || msgLower.includes("hyperparameters")) {
        targetTab = "tab-neural";
    } else if (msgLower.includes("broker") || msgLower.includes("system") || msgLower.includes("exchange")) {
        targetTab = "tab-settings";
    }
    
    // 1. Switch Navigation Tab if targetTab is identified
    if (targetTab) {
        const tabBtn = document.querySelector(`.nav-tab[data-tab="${targetTab}"]`);
        if (tabBtn) {
            tabBtn.click();
            
            // 2. Scroll to target element with visual highlighting if targetSelector exists
            if (targetSelector) {
                setTimeout(() => {
                    const card = document.getElementById(targetSelector);
                    if (card) {
                        card.scrollIntoView({ behavior: "smooth", block: "center" });
                        
                        // Add glow effect animation
                        const originalBorder = card.style.border;
                        const originalBoxShadow = card.style.boxShadow;
                        card.style.border = "1px solid var(--neon-blue)";
                        card.style.boxShadow = "0 0 20px rgba(0, 240, 255, 0.4)";
                        
                        setTimeout(() => {
                            card.style.border = originalBorder;
                            card.style.boxShadow = originalBoxShadow;
                        }, 2000);
                    }
                }, 200);
            }
        }
    }
    
    updateNotificationsUI();
}

// Update the badge count and render notifications in the bell dropdown list
function updateNotificationsUI() {
    const badge = document.getElementById("notification-badge");
    if (badge) {
        const activeUnread = notificationsList.filter(n => !n.read).length;
        if (activeUnread > 0) {
            badge.textContent = activeUnread;
            badge.style.display = "block";
        } else {
            badge.style.display = "none";
        }
    }
    
    const list = document.getElementById("notification-list");
    if (!list) return;
    
    if (notificationsList.length === 0) {
        list.innerHTML = `<div style="color: var(--text-secondary); text-align: center; padding: 20px 0;">No alerts logged.</div>`;
        return;
    }
    
    list.innerHTML = "";
    notificationsList.forEach(n => {
        const item = document.createElement("div");
        item.style.padding = "8px 10px";
        item.style.borderRadius = "6px";
        item.style.background = n.read ? "rgba(255,255,255,0.01)" : "rgba(255,255,255,0.04)";
        item.style.borderLeft = `3px solid ${n.type === "success" ? "var(--neon-green)" : n.type === "error" ? "var(--neon-red)" : "var(--neon-purple)"}`;
        item.style.cursor = "pointer";
        item.style.transition = "background 0.2s";
        item.style.display = "flex";
        item.style.flexDirection = "column";
        item.style.gap = "2px";
        
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                <span style="font-weight: 600; color: ${n.read ? 'var(--text-secondary)' : 'var(--text-primary)'};">${n.icon} Alert</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button class="copy-alert-btn" style="background: transparent; border: none; color: var(--neon-blue); cursor: pointer; font-size: 10px; padding: 2px 4px; border-radius: 4px; display: flex; align-items: center; gap: 2px; transition: var(--transition); opacity: 0.8;" title="Copy to clipboard">
                        <i data-lucide="copy" style="width: 10px; height: 10px;"></i>
                        Copy
                    </button>
                    <span style="font-size: 9px; opacity: 0.5;">${n.time}</span>
                </div>
            </div>
            <div style="color: ${n.read ? 'var(--text-muted)' : 'var(--text-secondary)'}; font-size: 11px; white-space: normal; word-break: break-word;">${n.message}</div>
        `;
        
        item.addEventListener("mouseenter", () => {
            item.style.background = "rgba(255,255,255,0.08)";
        });
        item.addEventListener("mouseleave", () => {
            item.style.background = n.read ? "rgba(255,255,255,0.01)" : "rgba(255,255,255,0.04)";
        });
        
        item.addEventListener("click", (e) => {
            e.stopPropagation();
            handleNotificationClick(n);
        });
        
        // Copy alert handler
        const copyBtn = item.querySelector(".copy-alert-btn");
        if (copyBtn) {
            copyBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(`[${n.time}] ${n.message}`)
                    .then(() => {
                        showToast("Alert copied to clipboard!", "success");
                    })
                    .catch(err => {
                        console.error("Copy failed: ", err);
                    });
            });
            copyBtn.addEventListener("mouseenter", () => {
                copyBtn.style.background = "rgba(0, 240, 255, 0.1)";
            });
            copyBtn.addEventListener("mouseleave", () => {
                copyBtn.style.background = "transparent";
            });
        }
        
        list.appendChild(item);
    });
    
    // Render in System Logs tab list/table if present
    const logsTbody = document.getElementById("logs-tab-alerts-tbody");
    if (logsTbody) {
        if (notificationsList.length === 0) {
            logsTbody.innerHTML = `<tr><td colspan="4" style="color: var(--text-secondary); text-align: center; padding: 20px;">No alerts logged in current session.</td></tr>`;
        } else {
            logsTbody.innerHTML = "";
            notificationsList.forEach(n => {
                const tr = document.createElement("tr");
                tr.style.borderBottom = "1px solid rgba(255,255,255,0.04)";
                tr.style.background = n.read ? "transparent" : "rgba(255,255,255,0.02)";
                
                let typeBadge = `<span style="color: var(--neon-blue); font-weight: bold;">INFO</span>`;
                if (n.type === "success") {
                    typeBadge = `<span style="color: var(--neon-green); font-weight: bold;">SUCCESS</span>`;
                } else if (n.type === "error") {
                    typeBadge = `<span style="color: var(--neon-red); font-weight: bold;">ERROR</span>`;
                }
                
                tr.innerHTML = `
                    <td style="padding: 8px 12px; font-weight: 600;">${typeBadge}</td>
                    <td style="padding: 8px 12px; color: var(--text-secondary); font-family: monospace;">${n.time}</td>
                    <td style="padding: 8px 12px; color: var(--text-primary); text-align: left;">${n.message}</td>
                    <td style="padding: 8px 12px; text-align: center;">
                        <button class="copy-alert-btn-table" style="background: transparent; border: none; color: var(--neon-blue); cursor: pointer; font-size: 10px; display: inline-flex; align-items: center; gap: 2px;" title="Copy to Clipboard">
                            <i data-lucide="copy" style="width: 10px; height: 10px;"></i>
                            Copy
                        </button>
                    </td>
                `;
                
                // Copy click handler
                const copyBtn = tr.querySelector(".copy-alert-btn-table");
                if (copyBtn) {
                    copyBtn.addEventListener("click", (e) => {
                        e.stopPropagation();
                        navigator.clipboard.writeText(`[${n.time}] ${n.message}`)
                            .then(() => showToast("Alert copied!", "success"))
                            .catch(err => console.error(err));
                    });
                }
                
                logsTbody.appendChild(tr);
            });
        }
    }
    
    // Refresh lucide icons inside dropdown list
    if (window.lucide) {
        lucide.createIcons({
            attrs: {
                class: 'lucide'
            },
            nameAttr: 'data-lucide'
        });
    }
}

// Notification Bell Dropdown Toggle Listeners
document.addEventListener("DOMContentLoaded", () => {
    // Initial render of persisted alerts
    updateNotificationsUI();

    const bellBtn = document.getElementById("notification-bell-btn");
    const dropdown = document.getElementById("notification-dropdown");
    const clearBtn = document.getElementById("clear-notifications-btn");
    
    if (bellBtn && dropdown) {
        bellBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const isOpen = dropdown.style.display === "block";
            dropdown.style.display = isOpen ? "none" : "block";
            
            // Mark all as read when opening
            if (!isOpen) {
                notificationsList.forEach(n => n.read = true);
                localStorage.setItem("nexustrader_alerts_history", JSON.stringify(notificationsList));
                updateNotificationsUI();
            }
        });
        
        // Close dropdown when clicking outside
        document.addEventListener("click", (e) => {
            if (!dropdown.contains(e.target) && e.target !== bellBtn && !bellBtn.contains(e.target)) {
                dropdown.style.display = "none";
            }
        });
    }
    
    if (clearBtn) {
        clearBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            notificationsList.length = 0;
            localStorage.removeItem("nexustrader_alerts_history");
            updateNotificationsUI();
            if (dropdown) dropdown.style.display = "none";
        });
    }
});

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
let activeTicker = "ETH-USD";
let isPortfolioMode = false;
let activePortfolioTimeframe = "1W";
const tickerLatest = {};
let activePosition = null;
let currentPrice = 0.0;
let balance = 100.0;
let equity = 100.0;
let initialBalance = 100.0;
let completedTrades = [];
let totalClosedPnL = 0.0;
let isStopped = false;
let currentWeights = {};
let globalTradingMode = "paper";
let globalBrokerName = "kraken";
let globalActiveBrains = {};
let weightsHistoryChart = null;

// Colors mapping for strategies
const strategyColors = {
    "EMA Crossover": "#00f0ff",
    "RSI Reversion": "#38bdf8",
    "BB Breakout": "#a855f7",
    "ML Random Forest": "#f43f5e",
    "Kalman Filter Trend": "#10b981",
    "Psych Liquidity Sweep": "#f59e0b",
    "News Sentiment": "#ec4899"
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
const elTradeLogBody = document.getElementById("recent-trades-list");
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
        case "sim_tick":
            handleSimTick(msg);
            break;
        case "trade_opened":
            handleTradeOpened(msg);
            break;
        case "sim_trade_opened":
            // Can be handled if needed, or ignored since we rely on sim_tick position updates
            break;
        case "trade_closed":
            handleTradeClosed(msg);
            break;
        case "sim_trade_closed":
            handleSimTradeClosed(msg);
            break;
        case "learning_update":
            handleLearningUpdate(msg);
            break;
        case "risk_mode_updated":
            if (elRiskSelect) elRiskSelect.value = msg.risk_mode;
            break;
        case "trading_mode_updated":
            globalTradingMode = msg.trading_mode;
            globalBrokerName = msg.broker;
            updateStatusBadge();
            break;
    }
}

// Process Init Message
function handleInitState(data) {
    if (data.active_brains) {
        globalActiveBrains = data.active_brains;
    }
    balance = data.balance;
    equity = data.equity !== undefined ? data.equity : data.balance;
    completedTrades = data.trades || [];
    if (data.initial_balance !== undefined) {
        initialBalance = data.initial_balance;
    }
    updateKpiBrainBadges();
    
    // Update initial neural memory diagnostic badge
    const elEpochs = document.getElementById("val-lifetime-steps");
    const elDna = document.getElementById("val-model-dna");
    if (elEpochs && data.lifetime_steps !== undefined) {
        elEpochs.textContent = data.lifetime_steps;
    }
    if (elDna && data.model_dna !== undefined) {
        elDna.textContent = data.model_dna;
    }
    
    // Initialize neural policy engine status log
    const logBox = document.getElementById("neural-log");
    if (logBox) {
        logBox.innerHTML = "";
        const timeStr = new Date().toLocaleTimeString();
        const entry = document.createElement("div");
        entry.style.marginBottom = "6px";
        entry.style.borderBottom = "1px solid rgba(255,255,255,0.02)";
        entry.style.paddingBottom = "4px";
        entry.innerHTML = `<span style="color:var(--text-muted)">[${timeStr}]</span> <span style="color:var(--neon-purple);font-weight:600;">[AI Policy Engine]</span> Loaded policy weights from DB. Neural network training active.`;
        logBox.appendChild(entry);
    }
    
    // Set active ticker default if not set
    if (data.ticker && !activeTicker) {
        activeTicker = data.ticker;
    }
    const elTitle = document.getElementById("chart-ticker-title");
    if (elTitle) elTitle.textContent = activeTicker;
    
    // Render Ticker Switcher tabs
    const switcherEl = document.getElementById("ticker-switcher-bar");
    if (switcherEl && data.tickers) {
        switcherEl.innerHTML = "";
        data.tickers.forEach(t => {
            const btn = document.createElement("button");
            btn.className = `ticker-tab ${t === activeTicker && !isPortfolioMode ? 'active' : ''}`;
            btn.id = `tab-${t}`;
            btn.setAttribute("data-ticker", t);
            btn.innerHTML = `
                <span class="ticker-tab-name">${t}</span>
                <span class="ticker-tab-price" id="tab-price-${t}">$0.00</span>
            `;
            btn.addEventListener("click", () => switchTicker(t));
            switcherEl.appendChild(btn);
        });
        
        // Add Portfolio Tab
        const portBtn = document.createElement("button");
        portBtn.className = `ticker-tab ${isPortfolioMode ? 'active' : ''}`;
        portBtn.id = "tab-portfolio";
        portBtn.innerHTML = `
            <span class="ticker-tab-name" style="color: var(--neon-purple); font-weight: bold;">💼 Portfolio</span>
            <span class="ticker-tab-price" id="tab-portfolio-equity">$${equity.toFixed(2)}</span>
        `;
        portBtn.addEventListener("click", () => switchPortfolioMode(true));
        switcherEl.appendChild(portBtn);

        // Toggle controls and status badges based on trading mode (live vs paper)
        globalTradingMode = data.trading_mode || "paper";
        globalBrokerName = data.broker || "kraken";
        updateStatusBadge();

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
            })
            .catch(err => console.error("Error loading historical candles:", err));
        
        if (data.risk_mode && elRiskSelect) {
            elRiskSelect.value = data.risk_mode;
        }
    }
}

function updateStatusBadge() {
    const statusTextEl = document.getElementById("status-text");
    const botStatusEl = document.getElementById("bot-status");
    const speedEl = document.getElementById("speed-slider") ? document.getElementById("speed-slider").parentElement : null;
    const playPauseBtn = document.getElementById("play-pause-btn");
    const resetBtn = document.getElementById("reset-btn");
    
    if (globalTradingMode === "live") {
        if (statusTextEl) statusTextEl.textContent = `Live (${globalBrokerName.toUpperCase()})`;
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
}

// Process Tick Message
function handleTick(data) {
    // Update simulation progress bar if active
    const simProgressContainer = document.getElementById("sim-progress-container");
    if (simProgressContainer) {
        if (data.sim_index !== undefined && data.sim_index !== null && data.sim_total) {
            simProgressContainer.style.display = "flex";
            const percent = (data.sim_index / data.sim_total) * 100;
            document.getElementById("sim-progress-bar").style.width = `${percent}%`;
            document.getElementById("sim-progress-label").textContent = `${data.sim_index} / ${data.sim_total} (${percent.toFixed(1)}%)`;
        } else {
            simProgressContainer.style.display = "none";
        }
    }

    // Store latest active brain
    if (data.active_brain) {
        globalActiveBrains[data.ticker] = data.active_brain;
        if (data.ticker === activeTicker) {
            updateKpiBrainBadges();
        }
    }

    // Store latest tick for this symbol
    tickerLatest[data.ticker] = data;
    
    // Update ticker price shown on switcher tab
    const tabPriceEl = document.getElementById(`tab-price-${data.ticker}`);
    if (tabPriceEl) {
        tabPriceEl.textContent = `$${data.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }
    // Update global balance & equity values whenever ANY tick arrives
    if (data.balance !== undefined) {
        balance = data.balance;
        elBalance.textContent = `$${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }
    if (data.equity !== undefined) {
        equity = data.equity;
        elEquity.textContent = `$${equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        const portEqEl = document.getElementById("tab-portfolio-equity");
        if (portEqEl) {
            portEqEl.textContent = `$${equity.toFixed(2)}`;
        }
    }
    
    // Update performance KPIs (realized + unrealized profit) in real-time
    updatePerformanceKPIs(completedTrades, equity);

    // Update cooldown status badge if it is active ticker
    if (data.ticker === activeTicker) {
        // Update neural memory diagnostics
        const elEpochs = document.getElementById("val-lifetime-steps");
        const elDna = document.getElementById("val-model-dna");
        if (elEpochs && data.lifetime_steps !== undefined) {
            elEpochs.textContent = data.lifetime_steps;
        }
        if (elDna && data.model_dna !== undefined) {
            elDna.textContent = data.model_dna;
        }

        const statusTextEl = document.getElementById("status-text");
        const botStatusEl = document.getElementById("bot-status");
        if (data.cooldown_active) {
            if (statusTextEl) statusTextEl.textContent = `Cooldown (${data.cooldown_remaining}m)`;
            if (botStatusEl) {
                botStatusEl.className = "status-badge stopped";
                botStatusEl.style.borderColor = "#f59e0b";
                botStatusEl.style.color = "#f59e0b";
            }
        } else {
            if (globalTradingMode === "live") {
                if (statusTextEl) statusTextEl.textContent = `Live (${globalBrokerName.toUpperCase()})`;
                if (botStatusEl) {
                    botStatusEl.className = "status-badge live";
                    botStatusEl.style.borderColor = "";
                    botStatusEl.style.color = "";
                }
            } else {
                if (statusTextEl) statusTextEl.textContent = "Simulating";
                if (botStatusEl) {
                    botStatusEl.className = "status-badge";
                    botStatusEl.style.borderColor = "";
                    botStatusEl.style.color = "";
                }
            }
        }
    }

    // If this tick belongs to another ticker, do not update the main chart or details cards
    if (data.ticker !== activeTicker) {
        return;
    }
    
    currentPrice = data.price;
    if (elPrice) elPrice.textContent = `$${currentPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
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
        
        elUnrealized.textContent = `Active Trade Profit: ${unrealizedDollar >= 0 ? '+' : ''}$${unrealizedDollar.toFixed(2)} (${unrealizedPercent.toFixed(2)}%)`;
        elUnrealized.className = unrealizedDollar >= 0 ? "kpi-sub color-green" : "kpi-sub color-red";
        
        renderActivePosition(activePosition, unrealizedDollar, unrealizedPercent);
    } else {
        elUnrealized.textContent = `Active Trade Profit: $0.00 (0.00%)`;
        elUnrealized.className = "kpi-sub";
        elPositionDetails.innerHTML = `<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Trade Currently Open</p>`;
    }
    // Process evaluation odds
    if (data.evaluation) {
        updateEvaluationWidget(data.evaluation, data.weighted_signal);
    }

    // Push chart data if not in portfolio mode
    if (!isPortfolioMode) {
        const timeLabel = data.timestamp.split(" ")[1] || data.timestamp.split("T")[1]?.slice(0, 5) || data.timestamp;
        
        if (chartLabels.length > 0 && chartLabels[chartLabels.length - 1] === timeLabel) {
            // Update last candle data point
            priceData[priceData.length - 1] = currentPrice;
            bbUpperData[bbUpperData.length - 1] = data.indicators.bb_upper;
            bbLowerData[bbLowerData.length - 1] = data.indicators.bb_lower;
        } else {
            // Append new candle data point
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
        }
        chart.update('none'); // Update without full recalculation transition for smooth updates
    }

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

function updateKpiBrainBadges() {
    const badges = document.querySelectorAll(".kpi-brain-badge");
    let text = "Portfolio Ensemble";
    if (!isPortfolioMode && activeTicker) {
        text = globalActiveBrains[activeTicker] || "Default Brain";
    }
    badges.forEach(b => {
        b.textContent = `🧠 ${text}`;
    });
}

function refreshNeuralCoreBrainSelector(ticker) {
    const dropdown = document.getElementById("select-active-brain-neural");
    const activeLabel = document.getElementById("kpi-neural-active-brain");
    const tickerDisplay = document.querySelector(".active-ticker-display-neural");
    
    if (tickerDisplay) tickerDisplay.textContent = ticker;
    if (!dropdown || !activeLabel) return;
    
    fetch(`/api/neural/brains?ticker=${ticker}&t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            dropdown.innerHTML = "";
            const brains = data.brains || [];
            const activeBrain = data.active_brain || "Default Brain";
            
            activeLabel.textContent = activeBrain;
            
            brains.forEach(b => {
                const opt = document.createElement("option");
                opt.value = b.name;
                opt.textContent = `${b.name} (${b.training_steps || 0} epochs)`;
                if (b.name === activeBrain) {
                    opt.selected = true;
                }
                dropdown.appendChild(opt);
            });
        })
        .catch(err => console.error("Error populating neural core brain selector:", err));
        
    fetch(`/api/neural/brain/auto_switch?ticker=${ticker}&t=${Date.now()}`)
        .then(res => res.json())
        .then(resData => {
            const autoSwitchCheck = document.getElementById("toggle-auto-switch-brain");
            if (autoSwitchCheck) {
                autoSwitchCheck.checked = resData.auto_switch;
            }
        })
        .catch(err => console.error("Error loading auto_switch configuration state:", err));
}

// Switch Active Ticker Handler
function switchTicker(ticker) {
    isPortfolioMode = false;
    activeTicker = ticker;
    updateKpiBrainBadges();
    refreshNeuralCoreBrainSelector(ticker);
    
    // Toggle UI visibility
    const elTf = document.getElementById("portfolio-timeframes");
    const elPr = document.getElementById("ticker-price-container");
    if (elTf) elTf.style.display = "none";
    if (elPr) elPr.style.display = "block";
    
    // Update tab classes
    document.querySelectorAll(".ticker-tab").forEach(tab => {
        if (tab.getAttribute("data-ticker") === ticker) {
            tab.classList.add("active");
        } else {
            tab.classList.remove("active");
        }
    });
    const portTab = document.getElementById("tab-portfolio");
    if (portTab) portTab.classList.remove("active");
    
    const elTitle = document.getElementById("chart-ticker-title");
    if (elTitle) elTitle.textContent = ticker;
    
    // Reset Chart.js dataset config
    if (chart && chart.data && chart.data.datasets) {
        if (chart.data.datasets[0]) {
            chart.data.datasets[0].label = 'Close Price';
            chart.data.datasets[0].borderColor = '#00f0ff';
        }
        if (chart.data.datasets[1]) {
            chart.data.datasets[1].label = 'BB Upper';
            chart.data.datasets[1].borderColor = 'rgba(168, 85, 247, 0.3)';
            chart.data.datasets[1].borderDash = [5, 5];
        }
        if (chart.data.datasets[2]) {
            chart.data.datasets[2].label = 'BB Lower';
            chart.data.datasets[2].borderColor = 'rgba(168, 85, 247, 0.3)';
            chart.data.datasets[2].borderDash = [5, 5];
        }
    }
    
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
        .then(data => {
            currentWeights = data.weights || data; // handle fallback for old structural format
            renderWeights(currentWeights);
            
            // Update neural diagnostics
            const elEpochs = document.getElementById("val-lifetime-steps");
            const elDna = document.getElementById("val-model-dna");
            if (elEpochs && data.lifetime_steps !== undefined) {
                elEpochs.textContent = data.lifetime_steps;
            }
            if (elDna && data.model_dna !== undefined) {
                elDna.textContent = data.model_dna;
            }
        })
        .catch(err => console.error("Error loading weights:", err));

    // Fetch weights history
    loadWeightsHistory(ticker);
    loadNeuralBrains(ticker);
        
    // Update active position/evaluation display for the new ticker from latest socket tick
    const tick = tickerLatest[ticker];
    if (tick) {
        handleTick(tick);
    } else {
        if (elPrice) elPrice.textContent = "$0.00";
        elUnrealized.textContent = "Active Trade Profit: $0.00 (0.00%)";
        elUnrealized.className = "kpi-sub";
        elPositionDetails.innerHTML = `<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Trade Currently Open</p>`;
    }
}

function switchPortfolioMode(enable) {
    if (!enable) return;
    isPortfolioMode = true;
    updateKpiBrainBadges();
    
    // Toggle UI visibility
    const elTf = document.getElementById("portfolio-timeframes");
    const elPr = document.getElementById("ticker-price-container");
    if (elTf) elTf.style.display = "flex";
    if (elPr) elPr.style.display = "none";
    
    // Update tab classes
    document.querySelectorAll(".ticker-tab").forEach(tab => tab.classList.remove("active"));
    const portTab = document.getElementById("tab-portfolio");
    if (portTab) portTab.classList.add("active");
    
    const elTitle = document.getElementById("chart-ticker-title");
    if (elTitle) elTitle.textContent = "Portfolio Equity & PnL";
    
    // Modify Chart.js dataset config
    if (chart && chart.data && chart.data.datasets) {
        if (chart.data.datasets[0]) {
            chart.data.datasets[0].label = 'Total Equity ($)';
            chart.data.datasets[0].borderColor = '#00f0ff';
        }
        if (chart.data.datasets[1]) {
            chart.data.datasets[1].label = 'Cumulative PnL ($)';
            chart.data.datasets[1].borderColor = '#10b981'; // green for profit
            chart.data.datasets[1].borderDash = []; // solid line
        }
        if (chart.data.datasets[2]) {
            chart.data.datasets[2].label = 'Initial Capital ($)';
            chart.data.datasets[2].borderColor = '#f59e0b'; // amber
            chart.data.datasets[2].borderDash = [4, 4]; // dashed line
        }
    }
    
    loadPortfolioHistory();
}

function loadPortfolioHistory() {
    if (!isPortfolioMode) return;
    
    chartLabels.length = 0;
    priceData.length = 0;
    bbUpperData.length = 0;
    bbLowerData.length = 0;
    
    fetch(`/api/portfolio/history?timeframe=${activePortfolioTimeframe}&t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            if (Array.isArray(data) && data.length > 0) {
                data.forEach(item => {
                    chartLabels.push(item.label);
                    priceData.push(item.equity);
                    bbUpperData.push(item.pnl);
                    bbLowerData.push(initialBalance);
                });
                chart.update();
            }
        })
        .catch(err => console.error("Error loading portfolio history:", err));
}

function handleTradeOpened(data) {
    activePosition = data.position;
    balance = data.balance;
    equity = data.equity !== undefined ? data.equity : data.balance;
    elBalance.textContent = `$${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elEquity.textContent = `$${equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Pulse card glow
    const card = document.getElementById("equity-card");
    card.classList.add("active");
    setTimeout(() => card.classList.remove("active"), 1000);
}

function handleTradeClosed(data) {
    activePosition = null;
    balance = data.balance;
    equity = data.equity !== undefined ? data.equity : data.balance;
    elBalance.textContent = `$${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elEquity.textContent = `$${equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Add trade to execution log and update stats
    renderTradeClosedState(data.trade);

    // Refresh brain list items & active specs indicators in real-time
    loadNeuralBrains(activeTicker);
    const runSimBtn = document.getElementById("btn-run-brain-sim");
    if (runSimBtn) {
        const selectedName = runSimBtn.getAttribute("data-brain-name");
        const selectedTicker = runSimBtn.getAttribute("data-brain-ticker");
        if (selectedName && selectedTicker) {
            selectBrainForSpecs(selectedName, selectedTicker);
        }
    }
}

function handleLearningUpdate(data) {
    currentWeights = data.weights;
    renderWeights(currentWeights);
    
    // Update memory diagnostics UI
    if (data.ticker === activeTicker) {
        const elEpochs = document.getElementById("val-lifetime-steps");
        const elDna = document.getElementById("val-model-dna");
        const elFooter = document.getElementById("neural-memory-footer");
        
        if (elEpochs && data.lifetime_steps !== undefined) {
            elEpochs.textContent = data.lifetime_steps;
        }
        if (elDna && data.model_dna !== undefined) {
            elDna.textContent = data.model_dna;
        }
        if (elFooter && data.last_save_time !== undefined) {
            elFooter.textContent = `Weights saved to local SQLite DB at ${data.last_save_time}.`;
            elFooter.style.color = "var(--neon-green)";
            setTimeout(() => {
                elFooter.textContent = "Weights synchronized to local SQLite DB.";
                elFooter.style.color = "var(--text-muted)";
            }, 5000);
        }
        
        // Reload history line chart and rebuild Policy Update Log dynamically from database
        loadWeightsHistory(data.ticker);
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
            <span>$${pos.entry_price.toFixed(2)}</span>
        </div>
        <div class="pos-row">
            <span>Profit Target</span>
            <span class="color-green">$${pos.take_profit.toFixed(2)}</span>
        </div>
        <div class="pos-row">
            <span>Max Loss Limit</span>
            <span class="color-red">$${pos.stop_loss.toFixed(2)}</span>
        </div>
        <div class="pos-row" style="background: rgba(255,255,255,0.05); font-weight:600;">
            <span>Current Profit</span>
            <span class="${isProfit ? 'color-green' : 'color-red'}">${isProfit ? '+' : ''}$${unrlDollar.toFixed(2)} (${unrlPct.toFixed(2)}%)</span>
        </div>
    `;
}

function updateEvaluationWidget(eval, signal) {
    const winProbPct = Math.round(eval.win_probability * 100);
    if (elProbGauge) elProbGauge.style.setProperty("--gauge-percent", `${(winProbPct / 100) * 360}deg`);
    if (elProbValue) elProbValue.textContent = `${winProbPct}%`;
    
    // Update BUY and SELL odds
    const elProbBuy = document.getElementById("val-prob-buy");
    const elProbSell = document.getElementById("val-prob-sell");
    const buyOdds = eval.direction === "BUY" ? winProbPct : (100 - winProbPct);
    const sellOdds = eval.direction === "SELL" ? winProbPct : (100 - winProbPct);
    if (elProbBuy) elProbBuy.textContent = `${buyOdds}%`;
    if (elProbSell) elProbSell.textContent = `${sellOdds}%`;
    
    if (elValEv) {
        elValEv.textContent = `${eval.expected_value >= 0 ? '+' : ''}$${eval.expected_value.toFixed(2)}`;
        elValEv.className = eval.expected_value >= 0 ? "color-green" : "color-red";
    }
    
    if (elValRr) elValRr.textContent = `1 : ${eval.risk_reward_ratio.toFixed(1)}`;
    if (elValKelly) elValKelly.textContent = `${(eval.kelly_fraction * 100).toFixed(1)}%`;
    if (elValSigStrength) elValSigStrength.textContent = `${Math.abs(signal * 100).toFixed(0)}%`;
    
    if (elViabilityBadge) {
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
}

function renderTradeLog(trades) {
    completedTrades = trades || [];
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
        row.style.cursor = "pointer";
        row.innerHTML = `
            <td>${timeStr}</td>
            <td>${t.symbol}</td>
            <td style="color: ${t.direction === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)'}; font-weight:600;">${t.direction}</td>
            <td>${t.quantity.toFixed(4)}</td>
            <td>$${t.entry_price.toFixed(2)}</td>
            <td>$${t.exit_price.toFixed(2)}</td>
            <td>72%</td> <!-- Estimated base -->
            <td class="${pnlColor}" style="font-weight:600;">${sign}$${t.pnl.toFixed(2)} (${(t.pnl_percent*100).toFixed(2)}%)</td>
            <td><span style="background: ${outcomeColor}; color: ${t.pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'}; padding: 4px 8px; border-radius: 4px; font-size:11px; font-weight:600;">${t.exit_reason.toUpperCase()}</span></td>
        `;
        row.addEventListener("click", () => {
            openTradeDetailsModal(t);
        });
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
    if (!trades) return;
    
    const winCount = trades.filter(t => t.pnl > 0).length;
    const wr = trades.length > 0 ? (winCount / trades.length) * 100 : 0.0;
    elWinrate.textContent = `${wr.toFixed(1)}%`;
    elTradeCount.textContent = `${trades.length} trades completed`;
    
    // Calculate Max Drawdown
    let peak = initialBalance;
    let maxDD = 0.0;
    let runningEquity = initialBalance;
    const chronologicalTrades = [...trades].sort((a, b) => a.exit_time - b.exit_time);
    for (const t of chronologicalTrades) {
        runningEquity += t.pnl;
        if (runningEquity > peak) {
            peak = runningEquity;
        }
        const dd = peak > 0 ? ((peak - runningEquity) / peak) * 100 : 0.0;
        if (dd > maxDD) {
            maxDD = dd;
        }
    }
    const elMaxDrawdown = document.getElementById("val-max-drawdown");
    if (elMaxDrawdown) {
        elMaxDrawdown.textContent = `${maxDD.toFixed(1)}%`;
    }
    
    let netPnL = 0.0;
    
    if (globalTradingMode === "live") {
        // In live mode, calculate net profit directly from Kraken portfolio value (current equity) - starting balance
        netPnL = currentEquity - initialBalance;
    } else {
        // 1. Calculate Realized PnL from trades
        const realizedPnL = trades.reduce((sum, t) => sum + t.pnl, 0);
        
        // 2. Calculate Unrealized PnL from active position
        let unrealizedPnL = 0.0;
        if (activePosition && currentPrice > 0) {
            const entry = activePosition.entry_price;
            const qty = activePosition.quantity;
            if (activePosition.direction === "BUY") {
                unrealizedPnL = (currentPrice - entry) * qty;
            } else {
                unrealizedPnL = (entry - currentPrice) * qty;
            }
        }
        netPnL = realizedPnL + unrealizedPnL;
    }
    
    const netPct = initialBalance > 0 ? (netPnL / initialBalance) * 100 : 0.0;
    
    elTotalPnL.textContent = `${netPnL >= 0 ? '+' : ''}$${netPnL.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elTotalPnLPercent.textContent = `${netPnL >= 0 ? '+' : ''}${netPct.toFixed(2)}% growth`;
    
    elTotalPnL.className = netPnL >= 0 ? "kpi-value color-green" : "kpi-value color-red";
    elTotalPnLPercent.className = netPnL >= 0 ? "kpi-sub color-green" : "kpi-sub color-red";
}

// User Interaction Listeners
if (elPlayPauseBtn) {
    elPlayPauseBtn.addEventListener("click", () => {
        isStopped = !isStopped;
        const action = isStopped ? "stop" : "start";
        const speed = elSpeedSlider ? parseFloat(elSpeedSlider.value) : 0.2;
        
        fetch(`/api/control?action=${action}&speed=${speed}&mode=${globalTradingMode === 'live' ? 'live' : 'simulation'}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (isStopped) {
                    if (elPlayPauseText) elPlayPauseText.textContent = "Resume";
                    const iconEl = elPlayPauseBtn.querySelector("i");
                    if (iconEl) iconEl.setAttribute("data-lucide", "play");
                    const stEl = document.getElementById("status-text");
                    if (stEl) stEl.textContent = "Paused";
                    const bsEl = document.getElementById("bot-status");
                    if (bsEl) bsEl.classList.add("stopped");
                } else {
                    if (elPlayPauseText) elPlayPauseText.textContent = "Pause";
                    const iconEl = elPlayPauseBtn.querySelector("i");
                    if (iconEl) iconEl.setAttribute("data-lucide", "pause");
                    const stEl = document.getElementById("status-text");
                    if (stEl) stEl.textContent = globalTradingMode === 'live' ? `Live (${globalBrokerName.toUpperCase()})` : "Simulating";
                    const bsEl = document.getElementById("bot-status");
                    if (bsEl) bsEl.classList.remove("stopped");
                }
                if (typeof lucide !== 'undefined') lucide.createIcons();
            });
    });
}

if (elSpeedSlider) {
    elSpeedSlider.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        if (elSpeedLabel) elSpeedLabel.textContent = `${val.toFixed(2)}s`;
        
        if (!isStopped) {
            fetch(`/api/control?action=start&speed=${val}&mode=${globalTradingMode === 'live' ? 'live' : 'simulation'}`, { method: 'POST' });
        }
    });
}

if (elResetBtn) {
    elResetBtn.addEventListener("click", () => {
        if (confirm("Are you sure you want to reset simulation, balance, and learning weights?")) {
            fetch("/api/control?action=reset", { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    priceData.length = 0;
                    chartLabels.length = 0;
                    bbUpperData.length = 0;
                    bbLowerData.length = 0;
                    if (chart) chart.update();
                
                isStopped = false;
                elPlayPauseText.textContent = "Pause";
                elPlayPauseBtn.querySelector("i").setAttribute("data-lucide", "pause");
                document.getElementById("status-text").textContent = "Simulating";
                document.getElementById("bot-status").classList.remove("stopped");
                lucide.createIcons();
                
                // Re-establish stats
                balance = 100.0;
                initialBalance = 100.0;
                elBalance.textContent = "$100.00";
                elEquity.textContent = "$100.00";
                elUnrealized.textContent = "Active Trade Profit: $0.00 (0.00%)";
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
}

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
            const elMaxDrawdownLimit = document.getElementById("val-max-drawdown-limit");
            if (elMaxDrawdownLimit) elMaxDrawdownLimit.textContent = `Limit: ${data.max_drawdown || 5.0}%`;
            if (elTpMultiplierInput) elTpMultiplierInput.value = data.tp_multiplier || 2.5;
            if (elSlMultiplierInput) elSlMultiplierInput.value = data.sl_multiplier || 1.5;
            const elNnLr = document.getElementById("setting-nn-lr");
            const elNnFloor = document.getElementById("setting-nn-floor");
            if (elNnLr) elNnLr.value = data.nn_lr || 0.15;
            if (elNnFloor) elNnFloor.value = data.nn_floor || 0.05;
            
            const elNnLrTab = document.getElementById("setting-nn-lr-tab");
            const elNnFloorTab = document.getElementById("setting-nn-floor-tab");
            if (elNnLrTab) elNnLrTab.value = data.nn_lr || 0.15;
            if (elNnFloorTab) elNnFloorTab.value = data.nn_floor || 0.05;
            
            const elNnLayersTab = document.getElementById("setting-nn-layers-tab");
            const elNnDimTab = document.getElementById("setting-nn-dim-tab");
            const elNnDropoutTab = document.getElementById("setting-nn-dropout-tab");
            const elNnOptimizerTab = document.getElementById("setting-nn-optimizer-tab");
            const elNnEpochsTab = document.getElementById("setting-nn-epochs-tab");
            if (elNnLayersTab) elNnLayersTab.value = data.nn_hidden_layers !== undefined ? data.nn_hidden_layers : 1;
            if (elNnDimTab) elNnDimTab.value = data.nn_hidden_dim !== undefined ? data.nn_hidden_dim : 12;
            if (elNnDropoutTab) elNnDropoutTab.value = data.nn_dropout !== undefined ? data.nn_dropout : 0.0;
            if (elNnOptimizerTab) elNnOptimizerTab.value = data.nn_optimizer || "Adam";
            if (elNnEpochsTab) elNnEpochsTab.value = data.nn_epochs !== undefined ? data.nn_epochs : 250;
            
            const elNnDiscountTab = document.getElementById("setting-nn-discount-tab");
            const elNnExplorationTab = document.getElementById("setting-nn-exploration-tab");
            if (elNnDiscountTab) elNnDiscountTab.value = data.nn_discount || 0.95;
            if (elNnExplorationTab) elNnExplorationTab.value = data.nn_exploration || 0.10;
            
            const elStartingCapital = document.getElementById("setting-starting-capital");
            if (elStartingCapital) elStartingCapital.value = data.initial_balance !== undefined ? data.initial_balance : 100.0;
        })
        .catch(err => console.error("Error loading system config:", err));

    // 3. Fetch Prompts configurations
    fetch(`/api/system/prompts?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            const elQuant = document.getElementById("prompt-quant-text");
            const elDev = document.getElementById("prompt-dev-text");
            const elBlog = document.getElementById("prompt-blog-text");
            const elNnPrompt = document.getElementById("prompt-nn-text");
            if (elQuant && data.prompt_quant) elQuant.value = data.prompt_quant;
            if (elDev && data.prompt_dev) elDev.value = data.prompt_dev;
            if (elBlog && data.prompt_blog) elBlog.value = data.prompt_blog;
            if (elNnPrompt && data.prompt_nn) elNnPrompt.value = data.prompt_nn;
            const elSentimentPrompt = document.getElementById("prompt-sentiment-text");
            const elRiskPrompt = document.getElementById("prompt-risk-text");
            const elAllocatorPrompt = document.getElementById("prompt-allocator-text");
            if (elSentimentPrompt && data.prompt_sentiment) elSentimentPrompt.value = data.prompt_sentiment;
            if (elRiskPrompt && data.prompt_risk) elRiskPrompt.value = data.prompt_risk;
            if (elAllocatorPrompt && data.prompt_allocator) elAllocatorPrompt.value = data.prompt_allocator;
        })
        .catch(err => console.error("Error loading prompt config:", err));

    // 4. Fetch Scheduling configurations
    fetch(`/api/system/schedule?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            const elDailyHour = document.getElementById("sched-daily-hour");
            const elWeeklyDay = document.getElementById("sched-weekly-day");
            const elWeeklyHour = document.getElementById("sched-weekly-hour");
            if (elDailyHour) elDailyHour.value = data.daily_agent_hour;
            if (elWeeklyDay) elWeeklyDay.value = data.weekly_agent_day;
            if (elWeeklyHour) elWeeklyHour.value = data.weekly_agent_hour;
            const elNnHour = document.getElementById("sched-nn-hour");
            if (elNnHour) elNnHour.value = data.nn_agent_hour || 1;
            const elSentHour = document.getElementById("sched-sent-hour");
            const elRiskHour = document.getElementById("sched-risk-hour");
            if (elSentHour) elSentHour.value = data.sentiment_agent_hour || 2;
            if (elRiskHour) elRiskHour.value = data.risk_auditor_hour || 3;
        })
        .catch(err => console.error("Error loading schedule config:", err));
}

// 1. Save Blog settings click handler
if (elSaveBlogConfigBtn) {
    elSaveBlogConfigBtn.addEventListener("click", () => {
        const enabled = elBlogEnabledCheck ? elBlogEnabledCheck.checked : true;
        const gitPush = elBlogGitPushCheck ? elBlogGitPushCheck.checked : true;
        const aiEnabled = elBlogAiCheck ? elBlogAiCheck.checked : false;
        const apiKey = elBlogApiKey ? elBlogApiKey.value.trim() : "";
        
        elSaveBlogConfigBtn.disabled = true;
        showToast("Saving Blogging Config...", "info");
        
        fetch(`/api/blog/config?enabled=${enabled}&ai_enabled=${aiEnabled}&api_key=${encodeURIComponent(apiKey)}&git_push_enabled=${gitPush}`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(data => {
            elSaveBlogConfigBtn.disabled = false;
            if (data.status === "success" || data.enabled !== undefined) {
                showToast("Automated Blogging configuration saved!", "success");
            } else {
                showToast("Failed to save blogging config: " + (data.error || "unknown error"), "error");
            }
        })
        .catch(err => {
            elSaveBlogConfigBtn.disabled = false;
            showToast("Error saving blogging configuration.", "error");
            console.error(err);
        });
    });
}

// 2. Save General System / Broker settings click handler
const elSaveSystemConfigBtn = document.getElementById("save-system-config-btn");
if (elSaveSystemConfigBtn) {
    elSaveSystemConfigBtn.addEventListener("click", () => {
        const tradingMode = elTradingModeSelect ? elTradingModeSelect.value : "paper";
        const broker = elBrokerSelect ? elBrokerSelect.value : "kraken";
        const exchangeApiKey = elApiKeyInput ? elApiKeyInput.value.trim() : "";
        const exchangeApiSecret = elApiSecretInput ? elApiSecretInput.value.trim() : "";
        const trailingStop = elTrailingStopCheck ? elTrailingStopCheck.checked : false;
        const cooldown = elCooldownInput ? parseFloat(elCooldownInput.value) : 4.0;
        const tpMultiplier = elTpMultiplierInput ? parseFloat(elTpMultiplierInput.value) : 2.5;
        const slMultiplier = elSlMultiplierInput ? parseFloat(elSlMultiplierInput.value) : 1.5;
        
        const elNnLr = document.getElementById("setting-nn-lr");
        const elNnFloor = document.getElementById("setting-nn-floor");
        const nnLr = elNnLr ? parseFloat(elNnLr.value) : 0.15;
        const nnFloor = elNnFloor ? parseFloat(elNnFloor.value) : 0.05;

        const elNnDiscountTab = document.getElementById("setting-nn-discount-tab");
        const elNnExplorationTab = document.getElementById("setting-nn-exploration-tab");
        const discountVal = elNnDiscountTab ? parseFloat(elNnDiscountTab.value) : 0.95;
        const explorationVal = elNnExplorationTab ? parseFloat(elNnExplorationTab.value) : 0.10;

        const elNnLayersTab = document.getElementById("setting-nn-layers-tab");
        const elNnDimTab = document.getElementById("setting-nn-dim-tab");
        const elNnDropoutTab = document.getElementById("setting-nn-dropout-tab");
        const elNnOptimizerTab = document.getElementById("setting-nn-optimizer-tab");
        const elNnEpochsTab = document.getElementById("setting-nn-epochs-tab");
        const hiddenLayers = elNnLayersTab ? parseInt(elNnLayersTab.value) : 1;
        const hiddenDim = elNnDimTab ? parseInt(elNnDimTab.value) : 12;
        const dropoutVal = elNnDropoutTab ? parseFloat(elNnDropoutTab.value) : 0.0;
        const optimizerVal = elNnOptimizerTab ? elNnOptimizerTab.value : "Adam";
        const epochsVal = elNnEpochsTab ? parseInt(elNnEpochsTab.value) : 250;

        const riskMode = elRiskSelect ? elRiskSelect.value : "conservative";
        const maxDrawdown = elMaxDrawdownInput ? parseFloat(elMaxDrawdownInput.value) : 5.0;
        
        const elStartingCapital = document.getElementById("setting-starting-capital");
        const startingCapital = elStartingCapital ? parseFloat(elStartingCapital.value) : 100.0;

        elSaveSystemConfigBtn.disabled = true;
        showToast("Saving Broker & Risk boundaries...", "info");
        
        fetch(`/api/system/config?trading_mode=${tradingMode}&risk_mode=${riskMode}&max_drawdown=${maxDrawdown}&broker=${broker}&api_key=${encodeURIComponent(exchangeApiKey)}&api_secret=${encodeURIComponent(exchangeApiSecret)}&trailing_stop=${trailingStop}&cooldown=${cooldown}&tp_multiplier=${tpMultiplier}&sl_multiplier=${slMultiplier}&nn_lr=${nnLr}&nn_floor=${nnFloor}&nn_discount=${discountVal}&nn_exploration=${explorationVal}&initial_balance=${startingCapital}&nn_hidden_layers=${hiddenLayers}&nn_hidden_dim=${hiddenDim}&nn_dropout=${dropoutVal}&nn_optimizer=${optimizerVal}&nn_epochs=${epochsVal}`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(data => {
            elSaveSystemConfigBtn.disabled = false;
            if (data.status === "success") {
                showToast("Broker and Risk boundaries updated successfully!", "success");
            } else {
                showToast("Failed to save broker settings: " + (data.error || "unknown error"), "error");
            }
        })
        .catch(err => {
            elSaveSystemConfigBtn.disabled = false;
            showToast("Error saving system settings.", "error");
            console.error(err);
        });
    });
}

const elSavePromptsBtn = document.getElementById("save-prompts-btn");
if (elSavePromptsBtn) {
    elSavePromptsBtn.addEventListener("click", () => {
        const elQuant = document.getElementById("prompt-quant-text");
        const elDev = document.getElementById("prompt-dev-text");
        const elBlog = document.getElementById("prompt-blog-text");
        const elNn = document.getElementById("prompt-nn-text");
        const elSent = document.getElementById("prompt-sentiment-text");
        const elRisk = document.getElementById("prompt-risk-text");
        const elAlloc = document.getElementById("prompt-allocator-text");
        
        elSavePromptsBtn.disabled = true;
        showToast("Saving Agent Prompts...", "info");
        
        const qVal = encodeURIComponent(elQuant ? elQuant.value : "");
        const dVal = encodeURIComponent(elDev ? elDev.value : "");
        const bVal = encodeURIComponent(elBlog ? elBlog.value : "");
        const nVal = encodeURIComponent(elNn ? elNn.value : "");
        const sVal = encodeURIComponent(elSent ? elSent.value : "");
        const rVal = encodeURIComponent(elRisk ? elRisk.value : "");
        const aVal = encodeURIComponent(elAlloc ? elAlloc.value : "");
        
        fetch(`/api/system/prompts?prompt_quant=${qVal}&prompt_dev=${dVal}&prompt_blog=${bVal}&prompt_nn=${nVal}&prompt_sentiment=${sVal}&prompt_risk=${rVal}&prompt_allocator=${aVal}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elSavePromptsBtn.disabled = false;
                if (data.status === "success") {
                    showToast("AI Agent prompt templates updated!", "success");
                } else {
                    showToast("Failed to save prompts: " + data.error, "error");
                }
            })
            .catch(err => {
                elSavePromptsBtn.disabled = false;
                showToast("Error saving prompts.", "error");
                console.error(err);
            });
    });
}

const elSaveScheduleBtn = document.getElementById("save-schedule-btn");
if (elSaveScheduleBtn) {
    elSaveScheduleBtn.addEventListener("click", () => {
        const elDailyHour = document.getElementById("sched-daily-hour");
        const elWeeklyDay = document.getElementById("sched-weekly-day");
        const elWeeklyHour = document.getElementById("sched-weekly-hour");
        
        elSaveScheduleBtn.disabled = true;
        showToast("Saving schedule timers...", "info");
        
        const elNnHour = document.getElementById("sched-nn-hour");
        const elSentHour = document.getElementById("sched-sent-hour");
        const elRiskHour = document.getElementById("sched-risk-hour");
        const dhVal = elDailyHour ? parseInt(elDailyHour.value) : 0;
        const wdVal = elWeeklyDay ? parseInt(elWeeklyDay.value) : 0;
        const whVal = elWeeklyHour ? parseInt(elWeeklyHour.value) : 23;
        const nhVal = elNnHour ? parseInt(elNnHour.value) : 1;
        const shVal = elSentHour ? parseInt(elSentHour.value) : 2;
        const rhVal = elRiskHour ? parseInt(elRiskHour.value) : 3;
        
        fetch(`/api/system/schedule?daily_agent_hour=${dhVal}&weekly_agent_day=${wdVal}&weekly_agent_hour=${whVal}&nn_agent_hour=${nhVal}&sentiment_agent_hour=${shVal}&risk_auditor_hour=${rhVal}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elSaveScheduleBtn.disabled = false;
                if (data.status === "success") {
                    showToast("Schedules updated & applied to crontab!", "success");
                } else {
                    showToast("Failed to save schedules: " + data.error, "error");
                }
            })
            .catch(err => {
                elSaveScheduleBtn.disabled = false;
                showToast("Error saving schedule.", "error");
                console.error(err);
            });
    });
}

if (elTriggerBlogBtn) {
    elTriggerBlogBtn.addEventListener("click", () => {
        elTriggerBlogBtn.disabled = true;
        showToast("Generating blog post & syncing reports...", "info");
        
        // Confirm mock options
        const useMock = confirm("Do you want to generate mock trading data before blogging? (Cancel to generate with actual DB data)");
        
        fetch(`/api/blog/generate?use_mock=${useMock}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elTriggerBlogBtn.disabled = false;
                if (data.status === "success") {
                    showToast("Blog report published successfully!", "success");
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
                    showToast("Failed to generate blog: " + data.error, "error");
                }
            })
            .catch(err => {
                elTriggerBlogBtn.disabled = false;
                showToast("Error generating blog.", "error");
                console.error(err);
            });
    });
}

// -------------------------------------------------------------
// AI Agent Action Click Event Handlers
// -------------------------------------------------------------
const elOptParamsBtn = document.getElementById("trigger-opt-params-btn-tab");
if (elOptParamsBtn) {
    elOptParamsBtn.addEventListener("click", () => {
        elOptParamsBtn.disabled = true;
        showToast("PhD Quant Agent optimizing ATR multipliers...", "info");
        fetch("/api/system/optimize/parameters", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elOptParamsBtn.disabled = false;
                if (data.status === "success") {
                    showToast("Quant optimization complete!", "success");
                    alert("Quant Parameter optimization complete!\n\n" + data.log);
                } else {
                    showToast("Quant optimization failed: " + data.error, "error");
                }
            })
            .catch(err => {
                elOptParamsBtn.disabled = false;
                showToast("Error running Quant optimizer.", "error");
                console.error(err);
            });
    });
}

const elSelfDevBtn = document.getElementById("trigger-self-dev-btn-tab");
if (elSelfDevBtn) {
    elSelfDevBtn.addEventListener("click", () => {
        elSelfDevBtn.disabled = true;
        showToast("Dev Architect iterating code improvements...", "info");
        fetch("/api/system/optimize/self_dev", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elSelfDevBtn.disabled = false;
                if (data.status === "success") {
                    showToast("Self-Dev code generation complete!", "success");
                    alert("AI Self-Development session completed successfully!\n\n" + data.log);
                } else {
                    showToast("Self-Development failed: " + data.error, "error");
                }
            })
            .catch(err => {
                elSelfDevBtn.disabled = false;
                showToast("Error running self-dev agent.", "error");
                console.error(err);
            });
    });
}

const elOptNnBtn = document.getElementById("trigger-opt-nn-btn-tab");
if (elOptNnBtn) {
    elOptNnBtn.addEventListener("click", () => {
        elOptNnBtn.disabled = true;
        showToast("NeuralCore tuning learning rate & bounds...", "info");
        fetch("/api/system/optimize/nn", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elOptNnBtn.disabled = false;
                if (data.status === "success") {
                    showToast("Neural optimizer completed!", "success");
                    alert("Neural Network self-tuning completed successfully!\n\n" + data.log);
                } else {
                    showToast("Neural core optimization failed: " + data.error, "error");
                }
            })
            .catch(err => {
                elOptNnBtn.disabled = false;
                showToast("Error tuning neural network.", "error");
                console.error(err);
            });
    });
}

document.querySelectorAll(".trigger-opt-sentiment-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        btn.disabled = true;
        showToast("Sentinel monitoring web feeds & sentiment...", "info");
        fetch("/api/system/optimize/sentiment", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                btn.disabled = false;
                if (data.status === "success") {
                    showToast("Sentiment source weights optimized!", "success");
                    alert("Sentiment source weights optimized successfully!\n\n" + data.log);
                } else {
                    showToast("Sentiment optimization failed: " + data.error, "error");
                }
            })
            .catch(err => {
                btn.disabled = false;
                showToast("Error optimizing sentiment.", "error");
                console.error(err);
            });
    });
});

document.querySelectorAll(".trigger-risk-audit-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        btn.disabled = true;
        showToast("Risk Auditor evaluating drawdowns...", "info");
        fetch("/api/system/optimize/risk_audit", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                btn.disabled = false;
                if (data.status === "success") {
                    showToast("Portfolio Risk Audit complete!", "success");
                    alert("Portfolio Risk Audit completed successfully!\n\n" + data.log);
                } else {
                    showToast("Risk audit failed: " + data.error, "error");
                }
            })
            .catch(err => {
                btn.disabled = false;
                showToast("Error running risk audit.", "error");
                console.error(err);
            });
    });
});

// Run All Agents shortcut button
const elRunAllBtn = document.getElementById("btn-run-all-agents");
if (elRunAllBtn) {
    elRunAllBtn.addEventListener("click", () => {
        const overlay = document.createElement("div");
        overlay.id = "agents-run-overlay";
        overlay.style.position = "fixed";
        overlay.style.top = "0";
        overlay.style.left = "0";
        overlay.style.width = "100%";
        overlay.style.height = "100%";
        overlay.style.background = "rgba(10, 15, 30, 0.85)";
        overlay.style.backdropFilter = "blur(20px)";
        overlay.style.zIndex = "1000000";
        overlay.style.display = "flex";
        overlay.style.justifyContent = "center";
        overlay.style.alignItems = "center";
        
        overlay.innerHTML = `
            <div class="glass-panel" style="width: 500px; padding: 30px; border-color: var(--neon-purple); text-align: left; box-shadow: 0 0 40px rgba(168,85,247,0.2); background: rgba(15,23,42,0.95);">
                <h3 style="font-size: 16px; font-weight: 700; color: var(--text-primary); margin-top: 0; margin-bottom: 5px; display: flex; align-items: center; gap: 8px;">
                    <i data-lucide="zap" style="color: var(--neon-purple); width: 18px; height: 18px;"></i>
                    Executing Autonomous Quant Team...
                </h3>
                <p style="font-size: 11px; color: var(--text-secondary); margin-bottom: 20px;">
                    Launching full team analysis pipeline concurrently. This takes up to 30 seconds.
                </p>
                
                <div style="display: flex; flex-direction: column; gap: 15px; margin-bottom: 25px;">
                    <div id="status-agent-quant" style="display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--text-primary);">
                        <span style="display: flex; align-items: center; gap: 10px;">📊 <strong>PhD Quant Agent:</strong> <span style="font-size: 11px; color: var(--text-secondary);">Tuning bounds...</span></span>
                        <span class="agent-spinner animate-pulse" style="color: var(--neon-purple); font-size: 11px; font-weight: bold; font-family: monospace;">RUNNING</span>
                    </div>
                    <div id="status-agent-nn" style="display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--text-primary);">
                        <span style="display: flex; align-items: center; gap: 10px;">🎓 <strong>NeuralCore Optimizer:</strong> <span style="font-size: 11px; color: var(--text-secondary);">Calibrating LR...</span></span>
                        <span class="agent-spinner animate-pulse" style="color: var(--neon-orange); font-size: 11px; font-weight: bold; font-family: monospace;">RUNNING</span>
                    </div>
                    <div id="status-agent-sent" style="display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--text-primary);">
                        <span style="display: flex; align-items: center; gap: 10px;">📡 <strong>NexusSentinel:</strong> <span style="font-size: 11px; color: var(--text-secondary);">Filtering news...</span></span>
                        <span class="agent-spinner animate-pulse" style="color: var(--neon-purple); font-size: 11px; font-weight: bold; font-family: monospace;">RUNNING</span>
                    </div>
                    <div id="status-agent-dev" style="display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--text-primary);">
                        <span style="display: flex; align-items: center; gap: 10px;">⚙️ <strong>Dev Architect:</strong> <span style="font-size: 11px; color: var(--text-secondary);">Running build test...</span></span>
                        <span class="agent-spinner animate-pulse" style="color: var(--neon-blue); font-size: 11px; font-weight: bold; font-family: monospace;">RUNNING</span>
                    </div>
                    <div id="status-agent-blog" style="display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--text-primary);">
                        <span style="display: flex; align-items: center; gap: 10px;">📝 <strong>NexusReporter AI:</strong> <span style="font-size: 11px; color: var(--text-secondary);">Writing blog...</span></span>
                        <span class="agent-spinner animate-pulse" style="color: var(--neon-green); font-size: 11px; font-weight: bold; font-family: monospace;">RUNNING</span>
                    </div>
                    <div id="status-agent-allocator" style="display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--text-primary);">
                        <span style="display: flex; align-items: center; gap: 10px;">⚖️ <strong>Asset Allocator:</strong> <span style="font-size: 11px; color: var(--text-secondary);">Balancing portfolio...</span></span>
                        <span class="agent-spinner animate-pulse" style="color: var(--neon-blue); font-size: 11px; font-weight: bold; font-family: monospace;">RUNNING</span>
                    </div>
                </div>
                
                <button class="btn" id="btn-close-agents-overlay" disabled style="width: 100%; justify-content: center; font-size: 12px;">Close Console</button>
            </div>
        `;
        document.body.appendChild(overlay);
        if (window.lucide) lucide.createIcons();
        
        const closeBtn = document.getElementById("btn-close-agents-overlay");
        
        const markSuccess = (id, msg) => {
            const row = document.getElementById(id);
            if (row) {
                row.querySelector("span span").textContent = msg;
                row.querySelector("span span").style.color = "var(--neon-green)";
                const spinner = row.querySelector(".agent-spinner");
                spinner.textContent = "COMPLETED";
                spinner.style.color = "var(--neon-green)";
                spinner.classList.remove("animate-pulse");
            }
        };
        
        const markFailed = (id, error) => {
            const row = document.getElementById(id);
            if (row) {
                row.querySelector("span span").textContent = error;
                row.querySelector("span span").style.color = "var(--neon-red)";
                const spinner = row.querySelector(".agent-spinner");
                spinner.textContent = "FAILED";
                spinner.style.color = "var(--neon-red)";
                spinner.classList.remove("animate-pulse");
            }
        };

        // 1. PhD Quant
        const p1 = fetch("/api/system/optimize/parameters", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    markSuccess("status-agent-quant", "Parameters optimized!");
                } else {
                    markFailed("status-agent-quant", data.error || "Failed");
                }
            })
            .catch(err => markFailed("status-agent-quant", "Connection error"));

        // 2. NN Optimizer
        const p2 = fetch("/api/system/optimize/nn", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    markSuccess("status-agent-nn", "Learning rate tuned!");
                } else {
                    markFailed("status-agent-nn", data.error || "Failed");
                }
            })
            .catch(err => markFailed("status-agent-nn", "Connection error"));

        // 3. Sentiment Optimizer
        const p3 = fetch("/api/system/optimize/sentiment", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    markSuccess("status-agent-sent", "Sentiment weights synced!");
                } else {
                    markFailed("status-agent-sent", data.error || "Failed");
                }
            })
            .catch(err => markFailed("status-agent-sent", "Connection error"));

        // 4. Dev Architect
        const p4 = fetch("/api/system/optimize/self_dev", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    markSuccess("status-agent-dev", "Codebase diagnostics updated!");
                } else {
                    markFailed("status-agent-dev", data.error || "Failed");
                }
            })
            .catch(err => markFailed("status-agent-dev", "Connection error"));

        // 5. NexusReporter AI (Blogger)
        const p5 = fetch("/api/blog/generate?use_mock=false", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    markSuccess("status-agent-blog", "Blog report published!");
                } else {
                    markFailed("status-agent-blog", data.error || "Failed");
                }
            })
            .catch(err => markFailed("status-agent-blog", "Connection error"));

        // 6. Ensemble Asset Allocator
        const p6 = fetch("/api/system/optimize/allocator", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    markSuccess("status-agent-allocator", "Asset weights rebalanced!");
                } else {
                    markFailed("status-agent-allocator", data.error || "Failed");
                }
            })
            .catch(err => markFailed("status-agent-allocator", "Connection error"));

        // Wait for all to finish
        Promise.all([p1, p2, p3, p4, p5, p6]).finally(() => {
            closeBtn.disabled = false;
            closeBtn.classList.add("btn-primary");
            closeBtn.addEventListener("click", () => {
                overlay.remove();
                fetch(`/api/trades?t=${Date.now()}`)
                    .then(res => res.json())
                    .then(trades => {
                        renderTradeLog(trades);
                        updatePerformanceKPIs(trades, equity);
                    });
            });
        });
    });
}

const elResetCooldownsBtn = document.getElementById("trigger-reset-cooldowns-btn-tab");
if (elResetCooldownsBtn) {
    elResetCooldownsBtn.addEventListener("click", () => {
        elResetCooldownsBtn.disabled = true;
        showToast("Clearing asset exchange cooldowns...", "info");
        fetch("/api/system/reset_cooldowns", { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                elResetCooldownsBtn.disabled = false;
                if (data.status === "success") {
                    showToast("System cooldowns cleared!", "success");
                } else {
                    showToast("Failed to clear cooldowns: " + data.error, "error");
                }
            })
            .catch(err => {
                elResetCooldownsBtn.disabled = false;
                showToast("Error resetting cooldowns.", "error");
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

// Loss Cooldowns Listener is defined above with the -tab suffix.

// Weights History Chart helper functions
function initWeightsHistoryChart() {
    const canvas = document.getElementById('weights-history-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    const datasets = Object.keys(strategyColors).map(stratName => {
        return {
            label: stratName,
            data: [],
            borderColor: strategyColors[stratName],
            backgroundColor: strategyColors[stratName] + "11",
            borderWidth: 1.5,
            tension: 0.2,
            pointRadius: 0,
            fill: false
        };
    });

    weightsHistoryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                x: {
                    display: false,
                    grid: {
                        display: false
                    }
                },
                y: {
                    min: 0,
                    max: 1.0,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.03)'
                    },
                    ticks: {
                        color: '#64748b',
                        callback: function(value) {
                            return (value * 100).toFixed(0) + "%";
                        }
                    }
                }
            }
        }
    });
}

function renderNeuralUpdateLog(history) {
    const logBox = document.getElementById("neural-log");
    if (!logBox) return;
    
    if (!Array.isArray(history) || history.length === 0) {
        logBox.innerHTML = `<div style="color:var(--text-muted); text-align:center; padding-top:20px;">No training steps recorded yet.</div>`;
        return;
    }
    
    logBox.innerHTML = "";
    
    // Sort chronological and process diffs (newest logs first)
    for (let i = history.length - 1; i >= 0; i--) {
        const current = history[i];
        const prev = i > 0 ? history[i-1] : null;
        const timeStr = new Date(current.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        let logText = "";
        if (!prev) {
            logText = "Model initialized with baseline equal weights.";
        } else {
            // Find the biggest change
            let shifts = [];
            Object.keys(current.weights).forEach(strat => {
                const currentWeight = current.weights[strat];
                const prevWeight = prev.weights[strat] !== undefined ? prev.weights[strat] : 0;
                const diff = (currentWeight - prevWeight) * 100;
                if (Math.abs(diff) >= 0.05) {
                    shifts.push({ name: strat, diff: diff });
                }
            });
            
            // Sort by absolute change magnitude
            shifts.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
            
            if (shifts.length === 0) {
                logText = "Model updated. No significant strategy weight shift.";
            } else {
                // Format top 2 shifts
                const formattedShifts = shifts.slice(0, 2).map(s => {
                    const sign = s.diff >= 0 ? "+" : "";
                    const color = s.diff >= 0 ? "var(--neon-green)" : "var(--neon-red)";
                    return `${s.name} (<span style="color: ${color}; font-weight:600;">${sign}${s.diff.toFixed(1)}%</span>)`;
                });
                logText = `Model trained. Shifts: ${formattedShifts.join(", ")}`;
            }
        }
        
        const entry = document.createElement("div");
        entry.style.marginBottom = "6px";
        entry.style.borderBottom = "1px solid rgba(255,255,255,0.02)";
        entry.style.paddingBottom = "4px";
        entry.style.lineHeight = "1.4";
        entry.innerHTML = `<span style="color:var(--text-muted)">[${timeStr}]</span> ${logText}`;
        logBox.appendChild(entry);
    }
}

function loadWeightsHistory(ticker) {
    if (!weightsHistoryChart) return;
    
    fetch(`/api/weights/history?ticker=${ticker}&t=${Date.now()}`)
        .then(res => res.json())
        .then(history => {
            if (Array.isArray(history)) {
                weightsHistoryChart.data.labels = [];
                weightsHistoryChart.data.datasets.forEach(ds => {
                    ds.data = [];
                });
                
                history.forEach((step, index) => {
                    const timeLabel = new Date(step.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                    weightsHistoryChart.data.labels.push(timeLabel);
                    
                    weightsHistoryChart.data.datasets.forEach(ds => {
                        const stratName = ds.label;
                        const val = step.weights[stratName] !== undefined ? step.weights[stratName] : 0;
                        ds.data.push(val);
                    });
                });
                
                weightsHistoryChart.update();
                
                // Rebuild policy log with persistent learning data
                renderNeuralUpdateLog(history);
            }
        })
        .catch(err => console.error("Error loading weights history:", err));
}

// App Startup
initChart();
initWeightsHistoryChart();
connectWebSocket();
loadBlogConfig();
loadWeightsHistory(activeTicker);

// Toggle Blog API Key visibility
const btnToggleKey = document.getElementById("toggle-blog-api-key-visibility");
const inputKey = document.getElementById("blog-api-key");
if (btnToggleKey && inputKey) {
    btnToggleKey.addEventListener("click", () => {
        const isPassword = inputKey.type === "password";
        inputKey.type = isPassword ? "text" : "password";
        btnToggleKey.innerHTML = isPassword ? `<i data-lucide="eye-off" style="width: 16px; height: 16px;"></i>` : `<i data-lucide="eye" style="width: 16px; height: 16px;"></i>`;
        lucide.createIcons();
    });
}

lucide.createIcons();

// Setup tab listeners for Exchange Portfolio
document.querySelectorAll(".portfolio-tab").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".portfolio-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        
        const tabName = btn.dataset.tab;
        document.querySelectorAll(".portfolio-tab-content").forEach(el => el.style.display = "none");
        document.getElementById(`tab-${tabName}`).style.display = "block";
    });
});

// Live Exchange holdings, positions, and open orders status polling
function updateExchangeStatus() {
    const elHoldingsContainer = document.getElementById("holdings-list-container");
    const elPositionsContainer = document.getElementById("positions-list-container");
    const elOpenOrdersContainer = document.getElementById("open-orders-list-container");
    
    if (!elHoldingsContainer || !elPositionsContainer || !elOpenOrdersContainer) return;
    
    fetch(`/api/exchange/status?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">${data.error}</p>`;
                elPositionsContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Error loading positions.</p>`;
                elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Error loading orders.</p>`;
                return;
            }
            
            if (data.message) {
                elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">${data.message}</p>`;
                elPositionsContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">${data.message}</p>`;
                elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">${data.message}</p>`;
                return;
            }
            
            // 1. Render holdings
            elHoldingsContainer.innerHTML = "";
            if (!data.holdings || data.holdings.length === 0) {
                elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">No holdings found.</p>`;
            } else {
                let totalUsd = 0;
                let usdCash = 0;
                data.holdings.forEach(h => {
                    totalUsd += h.value_usd;
                    if (h.asset === "USD" || h.asset === "ZUSD") {
                        usdCash = h.quantity;
                    }
                });
                
                if (globalTradingMode === "live") {
                    equity = totalUsd;
                    balance = usdCash;
                    if (elEquity) elEquity.textContent = `$${equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    if (elBalance) elBalance.textContent = `$${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    const portEqEl = document.getElementById("tab-portfolio-equity");
                    if (portEqEl) {
                        portEqEl.textContent = `$${equity.toFixed(2)}`;
                    }
                    updatePerformanceKPIs(completedTrades, equity);
                }
                
                data.holdings.forEach(h => {
                    const share = totalUsd > 0 ? ((h.value_usd / totalUsd) * 100).toFixed(1) : "0.0";
                    const row = document.createElement("div");
                    row.style.cssText = "display: flex; flex-direction: column; gap: 4px; padding: 8px 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 8px; font-size: 12px; transition: var(--transition);";
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: var(--text-primary);">${h.asset}</span>
                            <span style="font-weight: 600; color: var(--neon-blue);">$${h.value_usd.toFixed(2)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: var(--text-muted);">
                            <span>Qty: <span style="font-family: monospace;">${h.quantity.toFixed(4)}</span></span>
                            <span>Price: $${h.price_usd.toFixed(2)} (${share}%)</span>
                        </div>
                    `;
                    elHoldingsContainer.appendChild(row);
                });
                
                // Add Total row
                const totalRow = document.createElement("div");
                totalRow.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; margin-top: 6px; background: rgba(0, 240, 255, 0.04); border: 1px solid rgba(0, 240, 255, 0.15); border-radius: 8px; font-size: 12px; font-weight: 600;";
                totalRow.innerHTML = `
                    <span style="color: var(--text-primary);">Total Holdings Value</span>
                    <span style="color: var(--neon-blue); font-family: monospace;">$${totalUsd.toFixed(2)}</span>
                `;
                elHoldingsContainer.appendChild(totalRow);
            }
            
            // 2. Render open positions
            elPositionsContainer.innerHTML = "";
            if (!data.open_positions || data.open_positions.length === 0) {
                elPositionsContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 15px;">No active leverage positions.</p>`;
            } else {
                data.open_positions.forEach(p => {
                    const pnl = p.unrealizedPnl !== undefined && p.unrealizedPnl !== null ? p.unrealizedPnl : 0.0;
                    const pnlColor = pnl >= 0 ? "var(--neon-green)" : "var(--neon-red)";
                    const pnlSign = pnl >= 0 ? "+" : "";
                    const row = document.createElement("div");
                    row.style.cssText = "display: flex; flex-direction: column; gap: 4px; padding: 8px 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 8px; font-size: 12px; transition: var(--transition);";
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: var(--text-primary);">${p.symbol} <span style="font-size: 9px; padding: 2px 4px; border-radius: 4px; background: ${p.side === 'BUY' || p.side === 'LONG' ? 'rgba(16,185,129,0.1)' : 'rgba(244,63,94,0.1)'}; color: ${p.side === 'BUY' || p.side === 'LONG' ? 'var(--neon-green)' : 'var(--neon-red)'}; font-weight: bold;">${p.side}</span></span>
                            <span style="font-weight: 600; color: ${pnlColor};">${pnlSign}$${pnl.toFixed(2)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: var(--text-muted);">
                            <span>Entry: <span style="font-family: monospace;">$${p.entryPrice ? p.entryPrice.toFixed(2) : '-'}</span></span>
                            <span>Mark: <span style="font-family: monospace;">$${p.markPrice ? p.markPrice.toFixed(2) : '-'}</span> (${p.leverage ? p.leverage + 'x' : '1x'})</span>
                        </div>
                    `;
                    elPositionsContainer.appendChild(row);
                });
            }
            
            // 3. Render open orders
            elOpenOrdersContainer.innerHTML = "";
            if (!data.open_orders || data.open_orders.length === 0) {
                elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 15px;">No pending orders found.</p>`;
            } else {
                data.open_orders.forEach(o => {
                    const row = document.createElement("div");
                    row.style.cssText = "display: flex; flex-direction: column; gap: 4px; padding: 8px 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 8px; font-size: 12px; transition: var(--transition);";
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: var(--text-primary);">${o.symbol} <span style="font-size: 9px; padding: 2px 4px; border-radius: 4px; background: ${o.side === 'BUY' ? 'rgba(16,185,129,0.1)' : 'rgba(244,63,94,0.1)'}; color: ${o.side === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)'};">${o.side}</span></span>
                            <span style="font-weight: 600; color: var(--neon-blue);">$${o.price ? o.price.toFixed(2) : 'Market'}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: var(--text-muted);">
                            <span>Qty: <span style="font-family: monospace;">${o.amount.toFixed(4)}</span></span>
                            <span>Type: ${o.type}</span>
                        </div>
                    `;
                    elOpenOrdersContainer.appendChild(row);
                });
            }
        })
        .catch(err => {
            console.error("Error fetching exchange status:", err);
            elHoldingsContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Connection failed.</p>`;
            if (elPositionsContainer) elPositionsContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Connection failed.</p>`;
            elOpenOrdersContainer.innerHTML = `<p style="font-size: 11px; color: var(--neon-red); text-align: center; padding: 10px;">Connection failed.</p>`;
        });
}

// Initial pull and setup 15s interval
updateExchangeStatus();
setInterval(updateExchangeStatus, 15000);

// Timeframe button listener setup
document.querySelectorAll(".tf-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activePortfolioTimeframe = btn.dataset.tf;
        loadPortfolioHistory();
    });
});

// -------------------------------------------------------------
// Cybernetic Tab Navigation & Personified Layout Control
// -------------------------------------------------------------
const elNavTabs = document.querySelectorAll(".nav-tab");
const elTabContents = document.querySelectorAll(".tab-content");

elNavTabs.forEach(tab => {
    tab.addEventListener("click", () => {
        // Toggle active navigation tab
        elNavTabs.forEach(t => t.classList.remove("active"));
        tab.classList.add("active");

        // Toggle active content page
        const targetTabId = tab.getAttribute("data-tab");
        elTabContents.forEach(content => {
            if (content.id === targetTabId) {
                content.classList.add("active");
            } else {
                content.classList.remove("active");
            }
        });
        
        // Refresh charts or widgets if needed when visible
        if (targetTabId === "tab-neural") {
            loadWeightsHistory(activeTicker);
            loadNeuralBrains(activeTicker);
            refreshNeuralCoreBrainSelector(activeTicker);
        } else if (targetTabId === "tab-assets") {
            loadAssetManager();
        } else if (targetTabId === "tab-simulator") {
            loadNeuralBrains(activeTicker);
            if (!simChart) {
                initSimChart();
            }
        } else if (targetTabId === "tab-agents") {
            loadAgentLlmConfig();
        } else if (targetTabId === "tab-logs") {
            fetchSystemLogs();
        }
    });
});

// -------------------------------------------------------------
// Neural Core Parameter Adjustment Hook
// -------------------------------------------------------------
const elSaveNnParamsBtn = document.getElementById("save-nn-params-btn");
if (elSaveNnParamsBtn) {
    elSaveNnParamsBtn.addEventListener("click", () => {
        const elLrInput = document.getElementById("setting-nn-lr-tab");
        const elFloorInput = document.getElementById("setting-nn-floor-tab");
        if (!elLrInput || !elFloorInput) return;
        
        const lrVal = parseFloat(elLrInput.value);
        const floorVal = parseFloat(elFloorInput.value);
        
        const elDiscountInput = document.getElementById("setting-nn-discount-tab");
        const elExplorationInput = document.getElementById("setting-nn-exploration-tab");
        const discountVal = elDiscountInput ? parseFloat(elDiscountInput.value) : 0.95;
        const explorationVal = elExplorationInput ? parseFloat(elExplorationInput.value) : 0.10;
        
        const elLayersTab = document.getElementById("setting-nn-layers-tab");
        const elDimTab = document.getElementById("setting-nn-dim-tab");
        const elDropoutTab = document.getElementById("setting-nn-dropout-tab");
        const elOptimizerTab = document.getElementById("setting-nn-optimizer-tab");
        const elEpochsTab = document.getElementById("setting-nn-epochs-tab");
        const hiddenLayers = elLayersTab ? parseInt(elLayersTab.value) : 1;
        const hiddenDim = elDimTab ? parseInt(elDimTab.value) : 12;
        const dropoutVal = elDropoutTab ? parseFloat(elDropoutTab.value) : 0.0;
        const optimizerVal = elOptimizerTab ? elOptimizerTab.value : "Adam";
        const epochsVal = elEpochsTab ? parseInt(elEpochsTab.value) : 250;

        // Re-read other settings from dashboard controls or state to avoid overwriting them
        const tradingMode = document.getElementById("setting-trading-mode")?.value || "paper";
        const broker = document.getElementById("setting-broker")?.value || "kraken";
        const exchangeApiKey = document.getElementById("setting-api-key")?.value || "";
        const exchangeApiSecret = document.getElementById("setting-api-secret")?.value || "";
        const trailingStop = document.getElementById("setting-trailing-stop")?.checked || false;
        const cooldown = document.getElementById("setting-cooldown")?.value ? parseFloat(document.getElementById("setting-cooldown").value) : 4.0;
        const tpMultiplier = document.getElementById("setting-tp-multiplier")?.value ? parseFloat(document.getElementById("setting-tp-multiplier").value) : 2.5;
        const slMultiplier = document.getElementById("setting-sl-multiplier")?.value ? parseFloat(document.getElementById("setting-sl-multiplier").value) : 1.5;
        const riskMode = document.getElementById("risk-mode-select")?.value || "conservative";
        const maxDrawdown = document.getElementById("setting-max-drawdown")?.value ? parseFloat(document.getElementById("setting-max-drawdown").value) : 5.0;

        const elStartingCapital = document.getElementById("setting-starting-capital");
        const startingCapital = elStartingCapital ? parseFloat(elStartingCapital.value) : 100.0;

        elSaveNnParamsBtn.disabled = true;
        showToast("Saving Neural Hyperparameters...", "info");
        
        // Sync inputs with the other settings tab inputs so they stay updated
        const elNnLrOrig = document.getElementById("setting-nn-lr");
        const elNnFloorOrig = document.getElementById("setting-nn-floor");
        if (elNnLrOrig) elNnLrOrig.value = lrVal;
        if (elNnFloorOrig) elNnFloorOrig.value = floorVal;

        fetch(`/api/system/config?trading_mode=${tradingMode}&risk_mode=${riskMode}&max_drawdown=${maxDrawdown}&broker=${broker}&api_key=${encodeURIComponent(exchangeApiKey)}&api_secret=${encodeURIComponent(exchangeApiSecret)}&trailing_stop=${trailingStop}&cooldown=${cooldown}&tp_multiplier=${tpMultiplier}&sl_multiplier=${slMultiplier}&nn_lr=${lrVal}&nn_floor=${floorVal}&nn_discount=${discountVal}&nn_exploration=${explorationVal}&initial_balance=${startingCapital}&nn_hidden_layers=${hiddenLayers}&nn_hidden_dim=${hiddenDim}&nn_dropout=${dropoutVal}&nn_optimizer=${optimizerVal}&nn_epochs=${epochsVal}`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(data => {
            elSaveNnParamsBtn.disabled = false;
            if (data.status === "success") {
                showToast("Neural hyperparameters saved successfully!", "success");
            } else {
                showToast("Failed to save neural parameters: " + data.error, "error");
            }
        })
        .catch(err => {
            elSaveNnParamsBtn.disabled = false;
            showToast("Error saving neural settings.", "error");
            console.error("Error saving neural core settings:", err);
        });
    });
}

// Active Policy Brain Switcher on Neural Core tab
const elApplyActiveBrainNeuralBtn = document.getElementById("btn-apply-active-brain-neural");
if (elApplyActiveBrainNeuralBtn) {
    elApplyActiveBrainNeuralBtn.addEventListener("click", () => {
        const dropdown = document.getElementById("select-active-brain-neural");
        if (!dropdown) return;
        const name = dropdown.value;
        if (!name) return;
        
        activateNeuralBrain(name, activeTicker);
        
        setTimeout(() => {
            refreshNeuralCoreBrainSelector(activeTicker);
        }, 500);
    });
}

// Auto-Switch Brains Checkbox Listener
const elAutoSwitchBrainCheck = document.getElementById("toggle-auto-switch-brain");
if (elAutoSwitchBrainCheck) {
    elAutoSwitchBrainCheck.addEventListener("change", () => {
        const enable = elAutoSwitchBrainCheck.checked;
        fetch(`/api/neural/brain/auto_switch?ticker=${encodeURIComponent(activeTicker)}&enable=${enable}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    showToast(`Auto-Select Best Brain ${enable ? 'enabled' : 'disabled'}.`, "success");
                    if (enable) {
                        setTimeout(() => {
                            refreshNeuralCoreBrainSelector(activeTicker);
                        }, 500);
                    }
                } else {
                    showToast("Failed to toggle Auto-Select mode.", "error");
                }
            })
            .catch(err => {
                console.error("Error setting auto-switch state:", err);
                showToast("Error updating Auto-Select mode.", "error");
            });
    });
}

// -------------------------------------------------------------
// Populate NN values in Neural tab from config values on load
// -------------------------------------------------------------
setTimeout(() => {
    const elNnLrOrig = document.getElementById("setting-nn-lr");
    const elNnFloorOrig = document.getElementById("setting-nn-floor");
    const elLrInput = document.getElementById("setting-nn-lr-tab");
    const elFloorInput = document.getElementById("setting-nn-floor-tab");
    if (elNnLrOrig && elLrInput) elLrInput.value = elNnLrOrig.value;
    if (elNnFloorOrig && elFloorInput) elFloorInput.value = elNnFloorOrig.value;
}, 1500);

// -------------------------------------------------------------
// Neural Policy Brain Selection & Custom Training Handlers
// -------------------------------------------------------------
function loadNeuralBrains(ticker) {
    const listContainer = document.getElementById("neural-brains-list");
    const activeTickerEl = document.getElementById("brains-active-ticker");
    if (activeTickerEl) activeTickerEl.textContent = ticker;
    if (!listContainer) return;
    
    fetch(`/api/neural/brains?ticker=${ticker}&t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            listContainer.innerHTML = "";
            const brains = data.brains || [];
            const activeBrain = data.active_brain || "Default Brain";
            window.activeBrainName = activeBrain;
            
            if (brains.length === 0) {
                listContainer.innerHTML = `<div style="color: var(--text-secondary); text-align: center; padding: 15px 0; font-size: 11px;">No brains initialized.</div>`;
                return;
            }
            
            brains.forEach(b => {
                const isActive = b.name === activeBrain;
                const isDefault = ["Default Brain", "High-Freq Scalper", "Trend Follower"].includes(b.name);
                
                const item = document.createElement("div");
                item.className = "glass-panel";
                item.style.padding = "10px 12px";
                item.style.borderRadius = "8px";
                item.style.display = "flex";
                item.style.justifyContent = "space-between";
                item.style.alignItems = "center";
                item.style.border = isActive ? "1px solid var(--neon-purple)" : "1px solid var(--border-color)";
                item.style.background = isActive ? "rgba(168, 85, 247, 0.05)" : "rgba(255, 255, 255, 0.01)";
                item.style.fontSize = "11px";
                item.style.gap = "8px";
                item.style.marginBottom = "6px";
                item.style.cursor = "pointer";
                
                // Format creation date
                const dateStr = new Date(b.created_at * 1000).toLocaleString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
                
                item.innerHTML = `
                    <div style="flex: 1; display: flex; flex-direction: column; gap: 2px; overflow: hidden; text-align: left;">
                        <div style="display: flex; align-items: center; gap: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            <strong style="color: ${isActive ? 'var(--neon-purple)' : 'var(--text-primary)'};">${b.name}</strong>
                            ${isActive ? '<span style="font-size: 8px; color: var(--neon-purple); background: rgba(168,85,247,0.15); padding: 1px 4px; border-radius: 4px; font-weight: 700; text-transform: uppercase;">Active</span>' : ''}
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 9px; color: var(--text-muted); gap: 4px;">
                            <span>DNA: <span style="font-family: monospace; color: var(--neon-blue); font-weight: bold;">${b.model_dna}</span></span>
                            <span class="nt-tooltip">
                                Epochs: <span style="color: var(--neon-purple); font-weight: bold;">${b.training_steps || 0}</span>
                                <span class="nt-tooltiptext">Number of training updates this brain has had.</span>
                            </span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 9px; color: var(--text-muted); margin-top: 1px;">
                            <span>Efficacy: <span style="color: var(--neon-green); font-weight: bold;">${b.accumulated_trades ? ((b.accumulated_wins / b.accumulated_trades) * 100).toFixed(0) : 0}% WR</span> (${b.accumulated_trades || 0} trades)</span>
                            <span>${dateStr}</span>
                        </div>
                    </div>
                    <div style="display: flex; gap: 6px; align-items: center; flex-shrink: 0;">
                        ${!isActive ? `<button class="btn btn-activate-brain" style="padding: 3px 6px; font-size: 9px; height: auto; border-color: rgba(168,85,247,0.3); color: var(--neon-purple);">Activate</button>` : ''}
                        ${(!isDefault) ? `<button class="btn btn-delete-brain" style="padding: 3px 6px; font-size: 9px; height: auto; border-color: rgba(244,63,94,0.3); color: var(--neon-red);"><i data-lucide="trash-2" style="width: 10px; height: 10px;"></i></button>` : ''}
                    </div>
                `;
                
                // Add event listeners
                item.addEventListener("click", () => {
                    selectBrainForSpecs(b.name, ticker);
                });
                
                const actBtn = item.querySelector(".btn-activate-brain");
                if (actBtn) {
                    actBtn.addEventListener("click", (e) => {
                        e.stopPropagation();
                        activateNeuralBrain(b.name, ticker);
                    });
                }
                
                const delBtn = item.querySelector(".btn-delete-brain");
                if (delBtn) {
                    delBtn.addEventListener("click", (e) => {
                        e.stopPropagation();
                        deleteNeuralBrain(b.name, ticker);
                    });
                }
                
                listContainer.appendChild(item);
            });
            
            // Render active brain specs on load if available
            if (activeBrain) {
                selectBrainForSpecs(activeBrain, ticker);
            }
            
            lucide.createIcons();
        })
        .catch(err => console.error("Error loading neural brains:", err));
}

function selectBrainForSpecs(name, ticker) {
    const detailsPanel = document.getElementById("brain-details-panel");
    if (!detailsPanel) return;
    
    fetch(`/api/neural/brain/specs?name=${encodeURIComponent(name)}&ticker=${encodeURIComponent(ticker)}&t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                // Populate structural specs
                document.getElementById("details-brain-name").textContent = data.name + " Specs";
                document.getElementById("details-brain-dna").textContent = data.dna;
                
                // Format size
                const kbSize = (data.size_bytes / 1024).toFixed(2);
                document.getElementById("details-brain-size").textContent = `${kbSize} KB`;
                
                document.getElementById("details-brain-w1").textContent = data.w1_shape;
                document.getElementById("details-brain-w2").textContent = data.w2_shape;
                document.getElementById("details-brain-params").textContent = data.total_params;
                document.getElementById("details-brain-lr").textContent = `${data.learning_rate} / ${data.weight_floor}`;
                document.getElementById("details-brain-steps").textContent = data.training_steps || 0;
                
                // Populate trade attribution stats
                document.getElementById("stats-brain-trades").textContent = data.trade_count;
                document.getElementById("stats-brain-winrate").textContent = `${data.win_rate.toFixed(1)}%`;
                
                const pnlEl = document.getElementById("stats-brain-pnl");
                pnlEl.textContent = `${data.total_pnl >= 0 ? '+' : ''}$${data.total_pnl.toFixed(2)} (${data.avg_pnl_percent.toFixed(2)}%)`;
                pnlEl.style.color = data.total_pnl >= 0 ? "var(--neon-green)" : "var(--neon-red)";
                
                // Set metadata attributes on the Run Simulation button
                const runSimBtn = document.getElementById("btn-run-brain-sim");
                if (runSimBtn) {
                    runSimBtn.setAttribute("data-brain-name", data.name);
                    runSimBtn.setAttribute("data-brain-ticker", data.ticker);
                }

                // Display the panel
                detailsPanel.style.display = "block";
                
                // Refresh indicators inside details
                if (window.lucide) {
                    lucide.createIcons();
                }
            }
        })
        .catch(err => console.error("Error fetching brain specs:", err));
}

// Global scope functions for the button onclick triggers
window.activateNeuralBrain = function(name, ticker) {
    showToast(`Activating brain '${name}'...`, "info");
    
    // Set auto-switch checkbox to unchecked since user is doing a manual override
    const autoSwitchCheck = document.getElementById("toggle-auto-switch-brain");
    if (autoSwitchCheck) {
        autoSwitchCheck.checked = false;
    }
    
    fetch(`/api/neural/brain/activate?name=${encodeURIComponent(name)}&ticker=${encodeURIComponent(ticker)}&is_manual=true`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                showToast(`Policy brain '${name}' successfully activated!`, "success");
                globalActiveBrains[ticker] = name;
                updateKpiBrainBadges();
                loadNeuralBrains(ticker);
                
                // Update the active model DNA badge in NeuralCore Card
                fetch(`/api/neural/brains?ticker=${ticker}&t=${Date.now()}`)
                    .then(res => res.json())
                    .then(resData => {
                        const activeDetails = resData.brains.find(b => b.name === name);
                        if (activeDetails) {
                            const dnaBadge = document.getElementById("val-model-dna");
                            if (dnaBadge) dnaBadge.textContent = activeDetails.model_dna;
                        }
                    });
            } else {
                showToast(`Failed to activate brain: ${data.message}`, "error");
            }
        })
        .catch(err => {
            showToast("Error activating policy brain.", "error");
            console.error(err);
        });
};

window.deleteNeuralBrain = function(name, ticker) {
    if (!confirm(`Are you sure you want to delete custom brain '${name}'? This cannot be undone.`)) return;
    
    showToast(`Deleting brain '${name}'...`, "info");
    fetch(`/api/neural/brain/delete?name=${encodeURIComponent(name)}&ticker=${encodeURIComponent(ticker)}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                showToast(`Brain '${name}' deleted.`, "success");
                loadNeuralBrains(ticker);
            } else {
                showToast(`Failed to delete brain: ${data.message}`, "error");
            }
        })
        .catch(err => {
            showToast("Error deleting brain.", "error");
            console.error(err);
        });
};

// Hook up Clone Snapshot button
document.addEventListener("DOMContentLoaded", () => {
    const btnSnapshot = document.getElementById("btn-save-brain-snapshot");
    const btnTrain = document.getElementById("btn-train-new-brain");
    
    if (btnSnapshot) {
        btnSnapshot.addEventListener("click", () => {
            const name = prompt("Enter a name for this policy brain snapshot:", `Snapshot-${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}`);
            if (!name) return; // user cancelled
            
            showToast(`Saving brain snapshot '${name}'...`, "info");
            fetch(`/api/neural/brain/save?name=${encodeURIComponent(name.trim())}&ticker=${encodeURIComponent(activeTicker)}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.status === "success") {
                        showToast(`Saved brain snapshot: ${name}`, "success");
                        loadNeuralBrains(activeTicker);
                    } else {
                        showToast(`Failed to snapshot: ${data.message}`, "error");
                    }
                })
                .catch(err => {
                    showToast("Error saving brain snapshot.", "error");
                    console.error(err);
                });
        });
    }
    
    if (btnTrain) {
        btnTrain.addEventListener("click", () => {
            const name = prompt("Enter a name for your new training brain:", "Brain-Alpha");
            if (!name) return;
            
            showToast(`Initializing fresh network weights as '${name}'...`, "info");
            fetch(`/api/neural/brain/train?name=${encodeURIComponent(name.trim())}&ticker=${encodeURIComponent(activeTicker)}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.status === "success") {
                        showToast(`New training brain '${name}' initialized & activated!`, "success");
                        loadNeuralBrains(activeTicker);
                    } else {
                        showToast(`Failed to initialize new brain: ${data.message}`, "error");
                    }
                })
                .catch(err => {
                    showToast("Error creating fresh training brain.", "error");
                    console.error(err);
                });
        });
    }

    // Replay Simulation controls
    const speedRange = document.getElementById("sim-speed-range");
    const speedVal = document.getElementById("sim-speed-val");
    if (speedRange && speedVal) {
        speedRange.addEventListener("input", (e) => {
            speedVal.textContent = parseFloat(e.target.value).toFixed(2);
        });
    }

    const btnSimPlay = document.getElementById("btn-sim-play");
    const btnSimStop = document.getElementById("btn-sim-stop");
    
    if (btnSimPlay) {
        btnSimPlay.addEventListener("click", () => {
            const startDate = document.getElementById("sim-start-date")?.value || "";
            const endDate = document.getElementById("sim-end-date")?.value || "";
            const speed = speedRange ? parseFloat(speedRange.value) : 0.20;
            const brain = window.activeBrainName || "Default Brain";
            
            showToast(`Starting Backtest on ${activeTicker} using ${brain}...`, "info");
            
            fetch(`/api/control?action=start&mode=simulation&speed=${speed}&brain=${encodeURIComponent(brain)}&start_date=${startDate}&end_date=${endDate}`, {
                method: 'POST'
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "started") {
                    showToast("Backtest session started!", "success");
                } else {
                    showToast("Failed to start backtest.", "error");
                }
            })
            .catch(err => {
                showToast("Error starting backtest.", "error");
                console.error(err);
            });
        });
    }

    if (btnSimStop) {
        btnSimStop.addEventListener("click", () => {
            showToast("Resetting Backtest session...", "info");
            fetch(`/api/control?action=reset&speed=0.20`, {
                method: 'POST'
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "reset_completed") {
                    showToast("Backtest session reset successfully!", "success");
                } else {
                    showToast("Failed to reset backtest.", "error");
                }
            })
            .catch(err => {
                showToast("Error resetting backtest.", "error");
                console.error(err);
            });
        });
    }
});

// -------------------------------------------------------------
// System Diagnostic Terminal Log Retriever
// -------------------------------------------------------------
let logPollInterval = null;

function fetchSystemLogs() {
    const term = document.getElementById("system-terminal-output");
    if (!term) return;
    
    fetch(`/api/system/logs?limit=150&t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                // Store scroll position to keep focus if scrolled up
                const wasAtBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 30;
                term.textContent = data.logs || "No diagnostic log entries recorded.";
                
                // Auto scroll to bottom
                if (wasAtBottom) {
                    term.scrollTop = term.scrollHeight;
                }
            } else {
                term.textContent = `Diagnostic Terminal Error: ${data.message || "Unknown log source error"}`;
            }
        })
        .catch(err => {
            term.textContent = `Diagnostic Terminal Offline: Failed to establish link to host logs. ${err}`;
        });
}

// Hook up manual refresh button and auto-refresh loop
document.addEventListener("DOMContentLoaded", () => {
    const btnRefreshLogs = document.getElementById("btn-refresh-logs");
    const checkAutoRefresh = document.getElementById("log-auto-refresh");
    
    if (btnRefreshLogs) {
        btnRefreshLogs.addEventListener("click", () => {
            fetchSystemLogs();
            showToast("System diagnostic logs refreshed.", "success");
        });
    }
    
    // Auto-refresh loop
    logPollInterval = setInterval(() => {
        const isTabLogsActive = document.getElementById("tab-logs")?.classList.contains("active");
        const isAutoRefreshEnabled = checkAutoRefresh ? checkAutoRefresh.checked : false;
        
        if (isTabLogsActive && isAutoRefreshEnabled) {
            fetchSystemLogs();
        }
    }, 5000);

    // Wire Run Simulation shortcut button
    const runSimBtn = document.getElementById("btn-run-brain-sim");
    if (runSimBtn) {
        runSimBtn.addEventListener("click", () => {
            const name = runSimBtn.getAttribute("data-brain-name");
            const ticker = runSimBtn.getAttribute("data-brain-ticker");
            if (!name || !ticker) return;
            
            // Clear prior sim logs & charts
            simChartLabels.length = 0;
            simChartData.length = 0;
            simCompletedTrades.length = 0;
            if (simChart) {
                simChart.update();
            }
            const tbody = document.getElementById("sim-trade-log-body");
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-secondary); padding: 20px;">Initializing simulation...</td></tr>`;
            }
            
            showToast(`Initializing simulation loop on '${name}'...`, "info");
            
            // 1. Reset the simulation
            fetch("/api/control?action=reset", { method: 'POST' })
                .then(res => res.json())
                .then(() => {
                    // 2. Start simulation playback at speed=0.05 with the selected brain uniquely
                    fetch(`/api/control?action=start&mode=simulation&speed=0.05&brain=${encodeURIComponent(name)}`, { method: 'POST' })
                        .then(res => res.json())
                        .then(startData => {
                            if (startData.status === "started") {
                                showToast(`Simulation started uniquely on brain '${name}'!`, "success");
                                loadNeuralBrains(ticker);
                                
                                // Update status badge UI
                                isStopped = false;
                                elPlayPauseText.textContent = "Pause";
                                elPlayPauseBtn.querySelector("i").setAttribute("data-lucide", "pause");
                                document.getElementById("status-text").textContent = "Simulating";
                                document.getElementById("bot-status").classList.remove("stopped");
                                lucide.createIcons();
                            } else {
                                showToast("Failed to start simulation.", "error");
                            }
                        })
                        .catch(err => {
                            showToast("Error starting simulation loop.", "error");
                            console.error(err);
                        });
                })
                .catch(err => {
                    showToast("Error resetting simulation.", "error");
                    console.error(err);
                });
        });
    }
});

// -------------------------------------------------------------
// Closed Trade Details Modal Toggle Actions
// -------------------------------------------------------------
window.openTradeDetailsModal = function(t) {
    const modal = document.getElementById("trade-details-modal");
    if (!modal) return;
    
    document.getElementById("modal-trade-symbol").textContent = t.symbol;
    const sideEl = document.getElementById("modal-trade-side");
    sideEl.textContent = t.direction;
    sideEl.style.color = t.direction === "BUY" ? "var(--neon-green)" : "var(--neon-red)";
    
    document.getElementById("modal-trade-qty").textContent = t.quantity.toFixed(4);
    
    const pnlEl = document.getElementById("modal-trade-pnl");
    const sign = t.pnl >= 0 ? "+" : "";
    pnlEl.textContent = `${sign}$${t.pnl.toFixed(2)} (${(t.pnl_percent * 100).toFixed(2)}%)`;
    pnlEl.style.color = t.pnl >= 0 ? "var(--neon-green)" : "var(--neon-red)";
    
    document.getElementById("modal-trade-entry").textContent = `$${t.entry_price.toFixed(2)}`;
    document.getElementById("modal-trade-exit").textContent = `$${t.exit_price.toFixed(2)}`;
    
    const entryDate = new Date(t.entry_time * 1000);
    const exitDate = new Date(t.exit_time * 1000);
    document.getElementById("modal-trade-entry-time").textContent = entryDate.toLocaleString();
    document.getElementById("modal-trade-exit-time").textContent = exitDate.toLocaleString();
    
    document.getElementById("modal-trade-brain").textContent = t.policy_brain || "Default Brain";
    document.getElementById("modal-trade-reason").textContent = t.exit_reason.toUpperCase();
    
    // Parse and list strategy votes
    const signalsContainer = document.getElementById("modal-trade-signals");
    signalsContainer.innerHTML = "";
    let signals = [];
    try {
        signals = typeof t.strategy_signals === "string" ? JSON.parse(t.strategy_signals) : t.strategy_signals;
    } catch (e) {
        signals = [];
    }
    
    const strategies = ["EMA Crossover", "RSI Reversion", "Bollinger Bands Reversion", "Kalman Trend Filter", "Psychological Sweep", "ML Random Forest"];
    if (!signals || signals.length === 0) {
        signalsContainer.innerHTML = "<div>No strategy votes recorded.</div>";
    } else {
        strategies.forEach((strat, i) => {
            const vote = signals[i] || "NONE";
            let color = "var(--text-secondary)";
            if (vote === "BUY") color = "var(--neon-green)";
            if (vote === "SELL") color = "var(--neon-red)";
            
            const item = document.createElement("div");
            item.style.display = "flex";
            item.style.justifyContent = "space-between";
            item.innerHTML = `<span>${strat}:</span><span style="color: ${color}; font-weight: bold;">${vote}</span>`;
            signalsContainer.appendChild(item);
        });
    }
    
    // Parse and list sentiment details
    const sentimentContainer = document.getElementById("modal-trade-sentiment");
    sentimentContainer.innerHTML = "";
    let sentiment = {};
    try {
        sentiment = typeof t.sentiment_sources === "string" ? JSON.parse(t.sentiment_sources) : t.sentiment_sources;
    } catch (e) {
        sentiment = {};
    }
    
    if (!sentiment || Object.keys(sentiment).length === 0) {
        sentimentContainer.innerHTML = "<div>No macro sentiment data recorded at entry.</div>";
    } else {
        Object.keys(sentiment).forEach(source => {
            const score = sentiment[source];
            let color = "var(--text-secondary)";
            if (score > 0.1) color = "var(--neon-green)";
            if (score < -0.1) color = "var(--neon-red)";
            
            const item = document.createElement("div");
            item.style.display = "flex";
            item.style.justifyContent = "space-between";
            item.innerHTML = `<span>${source}:</span><span style="color: ${color};">${score >= 0 ? '+' : ''}${score.toFixed(2)}</span>`;
            sentimentContainer.appendChild(item);
        });
    }
    
    modal.style.display = "flex";
    
    // Refresh Lucide icons inside modal
    if (window.lucide) {
        lucide.createIcons();
    }
};

window.closeTradeDetailsModal = function() {
    const modal = document.getElementById("trade-details-modal");
    if (modal) modal.style.display = "none";
};

// -------------------------------------------------------------
// Separate Training Simulator Telemetry and Layout Routines
// -------------------------------------------------------------
let simChart;
let simChartLabels = [];
let simChartData = [];
let simCompletedTrades = [];

function initSimChart() {
    const canvas = document.getElementById('simChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    simChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: simChartLabels,
            datasets: [{
                label: 'Simulated Equity ($)',
                data: simChartData,
                borderColor: '#a855f7',
                borderWidth: 2,
                tension: 0.15,
                pointRadius: 2,
                fill: 'origin',
                backgroundColor: 'rgba(168, 85, 247, 0.05)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: 'rgba(255, 255, 255, 0.4)', font: { size: 9 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: 'rgba(255, 255, 255, 0.4)', font: { size: 9 } }
                }
            }
        }
    });
}

function handleSimTick(data) {
    const simProgressContainer = document.getElementById("sim-progress-container");
    if (simProgressContainer) {
        if (data.sim_index !== undefined && data.sim_index !== null && data.sim_total) {
            simProgressContainer.style.display = "flex";
            const percent = (data.sim_index / data.sim_total) * 100;
            document.getElementById("sim-progress-bar").style.width = `${percent}%`;
            document.getElementById("sim-progress-label").textContent = `${data.sim_index} / ${data.sim_total} (${percent.toFixed(1)}%)`;
        } else {
            simProgressContainer.style.display = "none";
        }
    }

    const simBalance = data.balance !== undefined ? data.balance : 100.0;
    const simEquity = data.equity !== undefined ? data.equity : simBalance;
    
    document.getElementById("val-sim-equity").textContent = `$${simEquity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    const label = data.timestamp ? data.timestamp.split(" ")[1] || data.timestamp.split("T")[1]?.slice(0, 5) || data.timestamp : "";
    if (simChartLabels.length === 0 || simChartLabels[simChartLabels.length - 1] !== label) {
        simChartLabels.push(label);
        simChartData.push(simEquity);
        if (simChartLabels.length > 200) {
            simChartLabels.shift();
            simChartData.shift();
        }
        if (simChart) {
            simChart.update();
        }
    }
    
    let unrealized = 0.0;
    let unrealizedPct = 0.0;
    const pos = data.position;
    if (pos && data.price > 0) {
        const entry = pos.entry_price;
        const qty = pos.quantity;
        if (pos.direction === "BUY") {
            unrealized = (data.price - entry) * qty;
        } else {
            unrealized = (entry - data.price) * qty;
        }
        unrealizedPct = entry > 0 ? (unrealized / (entry * qty)) * 100 : 0.0;
    }
    document.getElementById("val-sim-unrealized-pnl").textContent = `Sim Active PnL: ${unrealized >= 0 ? '+' : ''}$${unrealized.toFixed(2)} (${unrealizedPct.toFixed(2)}%)`;
}

function handleSimTradeClosed(data) {
    const trade = data.trade;
    if (!trade) return;
    simCompletedTrades.unshift(trade);
    renderSimTradeLog(simCompletedTrades);
    updateSimPerformanceKPIs(simCompletedTrades, data.equity);
}

function renderSimTradeLog(trades) {
    const tbody = document.getElementById("sim-trade-log-body");
    if (!tbody) return;
    tbody.innerHTML = "";
    if (trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-secondary); padding: 20px;">No simulation trades run yet. Start the simulator below.</td></tr>`;
        return;
    }
    
    trades.forEach(t => {
        const row = document.createElement("tr");
        row.style.borderBottom = "1px solid var(--border-color)";
        row.style.cursor = "pointer";
        row.style.transition = "background-color 0.15s";
        row.addEventListener("mouseover", () => row.style.backgroundColor = "rgba(255,255,255,0.02)");
        row.addEventListener("mouseout", () => row.style.backgroundColor = "transparent");
        
        const dateStr = new Date(t.exit_time * 1000).toLocaleTimeString();
        const pnlColor = t.pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        
        row.innerHTML = `
            <td style="padding: 8px 4px; color: var(--text-muted); font-family: monospace;">${dateStr}</td>
            <td style="padding: 8px 4px; font-weight: bold; color: var(--text-primary);">${t.symbol}</td>
            <td style="padding: 8px 4px;"><span class="badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}">${t.direction}</span></td>
            <td style="padding: 8px 4px; font-family: monospace;">$${t.entry_price.toFixed(2)}</td>
            <td style="padding: 8px 4px; font-family: monospace;">$${t.exit_price.toFixed(2)}</td>
            <td style="padding: 8px 4px; font-family: monospace;">${t.quantity.toFixed(4)}</td>
            <td style="padding: 8px 4px; text-align: right; font-weight: bold; color: ${pnlColor}; font-family: monospace;">${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}</td>
            <td style="padding: 8px 4px; text-align: right; font-weight: bold; color: ${pnlColor}; font-family: monospace;">${t.pnl_percent >= 0 ? '+' : ''}${(t.pnl_percent * 100).toFixed(2)}%</td>
        `;
        tbody.appendChild(row);
    });
}

function updateSimPerformanceKPIs(trades, currentEquity) {
    if (!trades) return;
    const winCount = trades.filter(t => t.pnl > 0).length;
    const wr = trades.length > 0 ? (winCount / trades.length) * 100 : 0.0;
    
    document.getElementById("val-sim-winrate").textContent = `${wr.toFixed(1)}%`;
    document.getElementById("val-sim-trade-count").textContent = `${trades.length} trades completed`;
    
    const realizedPnL = trades.reduce((sum, t) => sum + t.pnl, 0);
    const initialBal = 100.0;
    const netPct = (realizedPnL / initialBal) * 100;
    
    document.getElementById("val-sim-total-pnl").textContent = `${realizedPnL >= 0 ? '+' : ''}$${realizedPnL.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    document.getElementById("val-sim-total-pnl-percent").textContent = `${realizedPnL >= 0 ? '+' : ''}${netPct.toFixed(2)}% growth`;
}

// -------------------------------------------------------------
// Active Asset Manager Implementations
// -------------------------------------------------------------
function loadAssetManager() {
    const tbody = document.getElementById("asset-manager-tbody");
    if (!tbody) return;
    
    fetch(`/api/assets?t=${Date.now()}`)
        .then(res => res.json())
        .then(assets => {
            tbody.innerHTML = "";
            
            // Build add-asset-brain selector options dynamically from all unique brains in response
            const addAssetSelect = document.getElementById("add-asset-brain");
            if (addAssetSelect) {
                const uniqueBrains = new Set(["Default Brain"]);
                assets.forEach(asset => {
                    asset.brains.forEach(b => uniqueBrains.add(b));
                });
                addAssetSelect.innerHTML = `<option value="auto">Auto-Select (Best)</option>`;
                uniqueBrains.forEach(b => {
                    addAssetSelect.innerHTML += `<option value="${b}">${b}</option>`;
                });
            }
            
            assets.forEach(asset => {
                let brainOptions = `<option value="auto" ${asset.auto_switch ? 'selected' : ''}>Auto-Select (Best)</option>`;
                asset.brains.forEach(bName => {
                    brainOptions += `<option value="${bName}" ${(!asset.auto_switch && asset.active_brain === bName) ? 'selected' : ''}>${bName}</option>`;
                });
                
                const tr = document.createElement("tr");
                tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
                tr.innerHTML = `
                    <td style="padding: 10px; font-weight: 600; text-align: left;" title="Asset pair symbol name.">${asset.ticker}</td>
                    <td style="padding: 10px; text-align: center;">
                        <input type="checkbox" class="asset-active-check" data-ticker="${asset.ticker}" ${asset.is_active ? 'checked' : ''} style="accent-color: var(--neon-blue); cursor: pointer; width: 15px; height: 15px;" title="Active status checkbox.">
                    </td>
                    <td style="padding: 10px; text-align: center;">
                        <input type="number" class="asset-tp-input" data-ticker="${asset.ticker}" step="0.1" value="${asset.tp_multiplier}" style="background: #0f172b; border: 1px solid var(--border-color); color: var(--text-primary); padding: 4px; border-radius: 4px; width: 50px; text-align: center;" title="Custom Take Profit multiplier value.">
                    </td>
                    <td style="padding: 10px; text-align: center;">
                        <input type="number" class="asset-sl-input" data-ticker="${asset.ticker}" step="0.1" value="${asset.sl_multiplier}" style="background: #0f172b; border: 1px solid var(--border-color); color: var(--text-primary); padding: 4px; border-radius: 4px; width: 50px; text-align: center;" title="Custom Stop Loss multiplier value.">
                    </td>
                    <td style="padding: 10px; text-align: center;">
                        <input type="number" class="asset-kelly-input" data-ticker="${asset.ticker}" step="0.05" value="${asset.kelly_ceiling}" style="background: #0f172b; border: 1px solid var(--border-color); color: var(--text-primary); padding: 4px; border-radius: 4px; width: 50px; text-align: center;" title="Custom Kelly leverage size limit ceiling value.">
                    </td>
                    <td style="padding: 10px; text-align: center;">
                        <select class="asset-brain-select" data-ticker="${asset.ticker}" style="background: #0f172b; border: 1px solid var(--border-color); color: var(--text-primary); padding: 4px 8px; border-radius: 4px; font-family: inherit; font-size: 11px; width: 130px; cursor: pointer;" title="Lock custom brain or set to auto-select.">
                            ${brainOptions}
                        </select>
                    </td>
                    <td style="padding: 10px; text-align: center; display: flex; gap: 6px; justify-content: center; align-items: center;">
                        <button class="btn btn-save-asset" data-ticker="${asset.ticker}" style="padding: 4px 8px; font-size: 10px; border-color: var(--neon-green); color: var(--neon-green); background: rgba(0,255,100,0.05); cursor: pointer; border-radius: 4px;">Save</button>
                        <button class="btn btn-delete-asset" data-ticker="${asset.ticker}" style="padding: 4px 8px; font-size: 10px; border-color: var(--neon-red); color: var(--neon-red); background: rgba(255,0,0,0.05); cursor: pointer; border-radius: 4px;">Delete</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            
            // Wire save buttons
            tbody.querySelectorAll(".btn-save-asset").forEach(btn => {
                btn.addEventListener("click", () => {
                    const ticker = btn.getAttribute("data-ticker");
                    const is_active = tbody.querySelector(`.asset-active-check[data-ticker="${ticker}"]`).checked;
                    const tp_multiplier = parseFloat(tbody.querySelector(`.asset-tp-input[data-ticker="${ticker}"]`).value);
                    const sl_multiplier = parseFloat(tbody.querySelector(`.asset-sl-input[data-ticker="${ticker}"]`).value);
                    const kelly_ceiling = parseFloat(tbody.querySelector(`.asset-kelly-input[data-ticker="${ticker}"]`).value);
                    const brain_mode = tbody.querySelector(`.asset-brain-select[data-ticker="${ticker}"]`).value;
                    
                    saveAssetConfig(ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling, brain_mode);
                });
            });
            
            // Wire delete buttons
            tbody.querySelectorAll(".btn-delete-asset").forEach(btn => {
                btn.addEventListener("click", () => {
                    const ticker = btn.getAttribute("data-ticker");
                    if (confirm(`Are you sure you want to stop trading and delete asset '${ticker}'?`)) {
                        deleteAssetConfig(ticker);
                    }
                });
            });
        })
        .catch(err => console.error("Error loading asset manager:", err));
}

function saveAssetConfig(ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling, brain_mode = "auto") {
    showToast(`Saving asset '${ticker}'...`, "info");
    fetch(`/api/assets/save?ticker=${encodeURIComponent(ticker)}&is_active=${is_active}&tp_multiplier=${tp_multiplier}&sl_multiplier=${sl_multiplier}&kelly_ceiling=${kelly_ceiling}&brain_mode=${encodeURIComponent(brain_mode)}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                showToast(`Asset '${ticker}' successfully updated!`, "success");
                loadAssetManager();
            } else {
                showToast(`Error: ${data.message}`, "error");
            }
        })
        .catch(err => {
            console.error(err);
            showToast("Failed to save asset config.", "error");
        });
}

function deleteAssetConfig(ticker) {
    showToast(`Deleting asset '${ticker}'...`, "info");
    fetch(`/api/assets/delete?ticker=${encodeURIComponent(ticker)}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                showToast(`Asset '${ticker}' successfully removed!`, "success");
                loadAssetManager();
            } else {
                showToast(`Error: ${data.message}`, "error");
            }
        })
        .catch(err => {
            console.error(err);
            showToast("Failed to delete asset.", "error");
        });
}

// Add New Asset Listener
const btnAddAsset = document.getElementById("btn-add-asset");
if (btnAddAsset) {
    btnAddAsset.addEventListener("click", () => {
        const inputTicker = document.getElementById("add-asset-ticker");
        if (!inputTicker) return;
        const ticker = inputTicker.value.trim().toUpperCase();
        if (!ticker) {
            showToast("Please enter a valid ticker (e.g. ADA-USD).", "error");
            return;
        }
        
        const is_active = document.getElementById("add-asset-active").checked;
        const tp_multiplier = parseFloat(document.getElementById("add-asset-tp").value);
        const sl_multiplier = parseFloat(document.getElementById("add-asset-sl").value);
        const kelly_ceiling = parseFloat(document.getElementById("add-asset-kelly").value);
        const brain_mode = document.getElementById("add-asset-brain").value;
        
        saveAssetConfig(ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling, brain_mode);
        inputTicker.value = "";
    });
}

// Initialize on script load
setTimeout(() => {
    loadAssetManager();
    loadAgentLlmConfig();
}, 2000);

// -------------------------------------------------------------
// Agent LLM Provider Configuration Implementations
// -------------------------------------------------------------
function loadAgentLlmConfig() {
    const elTarget = document.getElementById("setting-agent-llm-target");
    const elProvider = document.getElementById("setting-agent-llm-provider");
    const elBaseUrl = document.getElementById("setting-agent-llm-base-url");
    const elModel = document.getElementById("setting-agent-llm-model");
    const elApiKey = document.getElementById("setting-agent-llm-api-key");
    
    if (!elProvider) return;
    
    const agent = elTarget ? elTarget.value : "default";
    
    fetch(`/api/system/agent_llm?agent=${encodeURIComponent(agent)}&t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            elProvider.value = data.provider;
            elBaseUrl.value = data.base_url || "";
            elModel.value = data.model || "";
            elApiKey.value = data.api_key || "";
            
            toggleAgentLlmInputs(data.provider);
        })
        .catch(err => console.error("Error loading agent LLM configuration:", err));
}

function toggleAgentLlmInputs(provider) {
    const containerUrl = document.getElementById("container-agent-llm-base-url");
    const containerModel = document.getElementById("container-agent-llm-model");
    const labelKey = document.getElementById("label-agent-llm-api-key");
    const inputUrl = document.getElementById("setting-agent-llm-base-url");
    const inputModel = document.getElementById("setting-agent-llm-model");
    
    if (!containerUrl || !containerModel || !labelKey) return;
    
    if (provider === "gemini") {
        containerUrl.style.display = "none";
        containerModel.style.display = "none";
        labelKey.textContent = "Gemini API Secret Key";
    } else if (provider === "openai") {
        containerUrl.style.display = "flex";
        containerModel.style.display = "flex";
        if (inputUrl && !inputUrl.value) inputUrl.value = "https://api.openai.com/v1";
        if (inputModel && !inputModel.value) inputModel.value = "gpt-4o";
        labelKey.textContent = "OpenAI API Secret Token";
    } else if (provider === "anthropic") {
        containerUrl.style.display = "flex";
        containerModel.style.display = "flex";
        if (inputUrl && !inputUrl.value) inputUrl.value = "https://api.anthropic.com/v1";
        if (inputModel && !inputModel.value) inputModel.value = "claude-3-5-sonnet-20241022";
        labelKey.textContent = "Anthropic API Secret Key";
    }
}

function saveAgentLlmConfig() {
    const elTarget = document.getElementById("setting-agent-llm-target");
    const provider = document.getElementById("setting-agent-llm-provider").value;
    const base_url = document.getElementById("setting-agent-llm-base-url").value;
    const model = document.getElementById("setting-agent-llm-model").value;
    const api_key = document.getElementById("setting-agent-llm-api-key").value;
    const agent = elTarget ? elTarget.value : "default";
    
    const saveBtn = document.getElementById("save-agent-llm-btn");
    if (saveBtn) saveBtn.disabled = true;
    
    showToast(`Saving LLM config for '${agent}'...`, "info");
    
    fetch(`/api/system/agent_llm?provider=${encodeURIComponent(provider)}&base_url=${encodeURIComponent(base_url)}&model=${encodeURIComponent(model)}&api_key=${encodeURIComponent(api_key)}&agent=${encodeURIComponent(agent)}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (saveBtn) saveBtn.disabled = false;
            if (data.status === "success") {
                showToast(`LLM config for '${agent}' saved successfully!`, "success");
                loadAgentLlmConfig();
            } else {
                showToast("Failed to save LLM config.", "error");
            }
        })
        .catch(err => {
            if (saveBtn) saveBtn.disabled = false;
            console.error(err);
            showToast("Error saving LLM config.", "error");
        });
}

const btnSaveAgentLlm = document.getElementById("save-agent-llm-btn");
if (btnSaveAgentLlm) {
    btnSaveAgentLlm.addEventListener("click", saveAgentLlmConfig);
}

const elTargetSelect = document.getElementById("setting-agent-llm-target");
if (elTargetSelect) {
    elTargetSelect.addEventListener("change", loadAgentLlmConfig);
}

const elProviderSelect = document.getElementById("setting-agent-llm-provider");
if (elProviderSelect) {
    elProviderSelect.addEventListener("change", (e) => {
        const inputUrl = document.getElementById("setting-agent-llm-base-url");
        const inputModel = document.getElementById("setting-agent-llm-model");
        if (inputUrl) inputUrl.value = "";
        if (inputModel) inputModel.value = "";
        toggleAgentLlmInputs(e.target.value);
    });
}
