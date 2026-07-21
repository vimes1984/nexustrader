/**
 * router.js — Tab navigation, global state, WebSocket connection
 * Lightweight SPA router for NexusTrader Dashboard v2
 */

const App = {
  // ── Global State ──
  state: {
    activeTab: 'dashboard',
    activeTicker: 'BTC-USD',
    tickers: [],
    tradingMode: 'live',
    isPaused: false,
    speed: 0.2,
    riskMode: 'aggressive',
    ws: null,
    chart: null,
    weightsChart: null,
    notifications: JSON.parse(localStorage.getItem('nt_notifications') || '[]'),
    unreadNotifications: 0,
  },

  // ── DOM Elements ──
  el: {},

  /** Debug log — only when debug mode is on */
  _debug(...args) {
    if (document.body.classList.contains('debug')) {
      console.log(...args);
    }
  },

  /** Initialize everything */
  async init() {
    this.cacheDOM();
    this.bindEvents();
    this.initNav();
    await this.loadInitState();
    this.connectWS();
    this.startPolling();
    this.renderNotifications();
    // Initialize all lucide icons (hamburger, nav, header, etc.)
    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
    App.emit('ready');
    // Restore tab from URL hash
    const hash = location.hash.replace('#', '');
    if (hash && hash !== 'dashboard') {
      const tabId = 'tab-' + hash;
      if (document.getElementById(tabId)) {
        this.switchTab(tabId);
      }
    }
    // Debug: log all nav-tab clicks to help diagnose nav issues
    document.querySelectorAll('.nav-tab').forEach((tab, i) => {
      const orig = tab.onclick;
      tab.addEventListener('click', function(e) {
        App._debug('NAV-CLICK:', tab.dataset.tab, 'target:', e.target.tagName, e.target.className);
      });
    });
    App._debug('initNav bound to', document.querySelectorAll('.nav-tab').length, 'nav items');
  },

  /** Cache frequently-used DOM elements */
  cacheDOM() {
    const byId = (id) => document.getElementById(id);
    this.el = {
      statusText: byId('status-text'),
      botStatus: byId('bot-status'),
      safetyBadge: byId('safety-badge'),
      safetyText: byId('safety-text'),
      equity: byId('val-equity'),
      balance: byId('val-balance'),
      unrealizedPnl: byId('val-unrealized-pnl'),
      winrate: byId('val-winrate'),
      tradeCount: byId('val-trade-count'),
      totalPnl: byId('val-total-pnl'),
      totalPnlPct: byId('val-total-pnl-percent'),
      tickerPrice: byId('ticker-price'),
      tickerChange: byId('ticker-change'),
      tickerTitle: byId('chart-ticker-title'),
      probValue: byId('prob-value'),
      probGauge: byId('prob-gauge'),
      evValue: byId('val-ev'),
      rrValue: byId('val-rr'),
      kellyValue: byId('val-kelly'),
      sigStrength: byId('val-sig-strength'),
      viabilityBadge: byId('viability-badge'),
      positionDetails: byId('position-details-container'),
      tradeLog: byId('recent-trades-list'),
      weightsContainer: byId('weights-container'),
      tickerSwitcher: byId('ticker-switcher-bar'),
      simProgress: byId('sim-progress-container'),
      simProgressBar: byId('sim-progress-bar'),
      simProgressLabel: byId('sim-progress-label'),
      toastContainer: byId('toast-container'),
      notificationBell: byId('notification-bell-btn'),
      notificationBadge: byId('notification-badge'),
      notificationDropdown: byId('notification-dropdown'),
      notificationList: byId('notification-list'),
      navDrawer: byId('nav-drawer'),
      navOverlay: byId('nav-drawer-overlay'),
    };
  },

  /** Bind global event handlers */
  bindEvents() {
    // Play/Pause
    const playPauseBtn = byId('play-pause-btn');
    if (playPauseBtn) playPauseBtn.addEventListener('click', () => this.togglePause());
    // Reset
    const resetBtn = byId('reset-btn');
    if (resetBtn) resetBtn.addEventListener('click', () => this.resetSim());
    // Speed slider
    const speedSlider = byId('speed-slider');
    if (speedSlider) {
      speedSlider.addEventListener('input', () => {
        this.state.speed = parseFloat(speedSlider.value);
        const label = byId('speed-label');
        if (label) label.textContent = this.state.speed.toFixed(2) + 's';
        App.emit('speed', this.state.speed);
      });
    }
    // Risk mode
    const riskSelect = byId('risk-mode-select');
    if (riskSelect) riskSelect.addEventListener('change', (e) => {
      this.setRiskMode(e.target.value);
    });
    // Navigation drawer
    const openBtn = byId('open-drawer-btn');
    if (openBtn) openBtn.addEventListener('click', () => this.openDrawer());
    const closeBtn = byId('close-drawer-btn');
    if (closeBtn) closeBtn.addEventListener('click', () => this.closeDrawer());
    if (this.el.navOverlay) this.el.navOverlay.addEventListener('click', () => this.closeDrawer());
    // Notification bell
    if (this.el.notificationBell) this.el.notificationBell.addEventListener('click', () => this.toggleNotifications());
    const clearNotifBtn = byId('clear-notifications-btn');
    if (clearNotifBtn) clearNotifBtn.addEventListener('click', () => this.clearNotifications());
    // Dev debug toggle
    byId('btn-dev-toggle')?.addEventListener('click', () => {
      document.body.classList.toggle('debug');
      const isDebug = document.body.classList.contains('debug');
      this.toast(isDebug ? 'Debug mode ON' : 'Debug mode OFF', 'info');
      // Store preference
      localStorage.setItem('nt_debug', isDebug ? '1' : '0');
    });
    // Restore debug preference
    if (localStorage.getItem('nt_debug') === '1') {
      document.body.classList.add('debug');
    }
    // Close drawer on outside click
    document.addEventListener('click', (e) => {
      try {
        if (this.el.notificationDropdown && this.el.notificationDropdown.style.display === 'flex' &&
            !e.target.closest('.notification-dropdown-container')) {
          this.el.notificationDropdown.style.display = 'none';
        }
      } catch(_) { /* silent */ }
    });
  },

  /** Initialize tab navigation */
  initNav() {
    const tabs = document.querySelectorAll('.nav-tab');
    if (tabs.length === 0) {
      console.error('initNav: NO .nav-tab elements found in DOM!');
      return;
    }
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const tabId = tab.dataset.tab;
        if (tabId) {
          this.switchTab(tabId);
        }
        this.closeDrawer();
      });
    });
  },

  /** Switch to a tab */
  switchTab(tabId) {
    try {
      App._debug('switchTab called:', tabId);
      // Update nav buttons
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      const btn = document.querySelector('.nav-tab[data-tab="' + tabId + '"]');
      if (btn) btn.classList.add('active');

      // Show/hide tab content
      const allTabs = document.querySelectorAll('.tab-content');
      App._debug('  found', allTabs.length, 'tab-content divs');
      allTabs.forEach(c => c.style.display = 'none');
      const content = document.getElementById(tabId);
      if (content) {
        content.style.display = 'block';
        App._debug('  switched to', tabId);
      } else {
        console.error('  tab not found:', tabId);
      }

      this.state.activeTab = tabId.replace('tab-', '');
      App.emit('tabChange', this.state.activeTab);
      // Update URL hash for bookmarkability
      if (typeof history !== 'undefined') {
        history.replaceState(null, '', '#' + this.state.activeTab);
      }
      // Re-render icons in the newly visible tab
      if (typeof lucide !== 'undefined') {
        setTimeout(() => lucide.createIcons(), 50);
      }
    } catch(e) {
      console.error('switchTab error:', e);
    }
  },

  /** Toggle play/pause */
  async togglePause() {
    this.state.isPaused = !this.state.isPaused;
    const btn = byId('play-pause-btn');
    const icon = btn.querySelector('i');
    const text = byId('play-pause-text');
    if (this.state.isPaused) {
      icon.setAttribute('data-lucide', 'play');
      text.textContent = 'Play';
    } else {
      icon.setAttribute('data-lucide', 'pause');
      text.textContent = 'Pause';
    }
    lucide.createIcons();
    await API.control(this.state.isPaused ? 'pause' : 'resume');
  },

  /** Reset simulation */
  async resetSim() {
    if (!confirm('Reset simulation? This clears all trade history.')) return;
    try { await API.control('reset'); this.toast('Simulation reset', 'info'); }
    catch (e) { this.toast('Reset failed: ' + e.message, 'error'); }
  },

  /** Set risk mode */
  async setRiskMode(mode) {
    try {
      await API.setRiskMode(mode);
      this.state.riskMode = mode;
      this.toast(`Risk mode: ${mode}`, 'success');
    } catch (e) {
      this.toast('Risk mode change failed', 'error');
    }
  },

  /** Open nav drawer */
  openDrawer() {
    if (this.el.navDrawer) this.el.navDrawer.style.left = '0';
    if (this.el.navOverlay) this.el.navOverlay.style.display = 'block';
  },

  /** Close nav drawer */
  closeDrawer() {
    if (this.el.navDrawer) this.el.navDrawer.style.left = '-280px';
    if (this.el.navOverlay) this.el.navOverlay.style.display = 'none';
  },

  /** Load initial state from API */
  async loadInitState() {
    try {
      const data = await API.initState();
      this.state.tickers = data.tickers || [];
      this.state.tickerPrices = data.ticker_prices || {};
      this.state.tradingMode = data.trading_mode || 'live';
      this.state.riskMode = data.risk_mode || 'aggressive';
      this.state.activeTicker = this.state.tickers[0] || 'BTC-USD';

      // Update UI
      byId('risk-mode-select').value = this.state.riskMode;
      this.updateStatusBadge();

      // Set price for active ticker
      const prices = data.ticker_prices || {};
      if (prices[this.state.activeTicker] && this.el.tickerPrice) {
        const price = prices[this.state.activeTicker];
        this.el.tickerPrice.textContent = '$' + Number(price).toFixed(2);
      }

      // Render ticker switcher
      this.renderTickerSwitcher();

      App.emit('initState', data);
    } catch (e) {
      console.error('Init failed:', e);
      this.toast('Failed to load initial state', 'error');
    }
  },

  /** Render ticker switcher tabs */
  renderTickerSwitcher() {
    const container = this.el.tickerSwitcher;
    if (!container) return;
    container.innerHTML = '';

    // Pre-load ticker prices
    const prices = this.state.tickerPrices || {};

    this.state.tickers.forEach(t => {
      const btn = document.createElement('button');
      btn.className = 'ticker-tab';
      btn.dataset.ticker = t;
      const price = prices[t] ? '$' + Number(prices[t]).toFixed(2) : '$0.00';
      btn.innerHTML = '<span class="ticker-tab-name">' + t + '</span><span class="ticker-tab-price" id="tab-price-' + t + '">' + price + '</span>';
      btn.addEventListener('click', () => this.selectTicker(t));
      container.appendChild(btn);
    });

    // Portfolio tab
    const portBtn = document.createElement('button');
    portBtn.id = 'tab-portfolio';
    portBtn.className = 'ticker-tab';
    portBtn.innerHTML = '<span class="ticker-tab-name" style="color:var(--neon-purple);font-weight:700">Portfolio</span><span class="ticker-tab-price" id="tab-portfolio-equity">$0.00</span>';
    portBtn.addEventListener('click', () => this.selectTicker('portfolio'));
    container.appendChild(portBtn);

    this.selectTicker(this.state.activeTicker || this.state.tickers[0]);
  },

  /** Select a ticker */
  selectTicker(ticker) {
    this.state.activeTicker = ticker;
    // Update tab buttons
    document.querySelectorAll('.ticker-tab').forEach(b => {
      b.classList.toggle('active-ticker', b.dataset.ticker === ticker || (ticker === 'portfolio' && b.id === 'tab-portfolio'));
    });
    // Update title
    if (this.el.tickerTitle) {
      this.el.tickerTitle.textContent = ticker === 'portfolio' ? 'Portfolio Overview' : ticker;
    }
    App.emit('tickerChange', ticker);
  },

  /** Connect WebSocket */
  connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${location.host}/ws`;
    this.state.ws = new WebSocket(wsUrl);
    
    this.state.ws.onopen = () => {
      this.el.botStatus.classList.remove('stopped');
      this.el.statusText.textContent = this.state.tradingMode === 'live' ? 'LIVE' : 'Simulating';
    };

    this.state.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        App.emit('wsMessage', msg);
      } catch (e) { /* ignore parse errors */ }
    };

    this.state.ws.onclose = () => {
      this.el.statusText.textContent = 'Disconnected';
      this.el.botStatus.classList.add('stopped');
      // Reconnect after 5s
      setTimeout(() => this.connectWS(), 5000);
    };

    this.state.ws.onerror = () => {
      this.el.statusText.textContent = 'Error';
      this.el.botStatus.classList.add('stopped');
    };
  },

  /** Start periodic polling */
  startPolling() {
    // Safety status every 5s
    setInterval(() => this.pollSafety(), 5000);
    // Full status every 10s
    setInterval(() => this.pollStatus(), 10000);
  },

  /** Poll safety status */
  async pollSafety() {
    try {
      const data = await API.safetyStatus();
      // API returns {kill_switch: {tripped: bool, ...}}
      const isTripped = data.kill_switch?.tripped === true;
      if (isTripped) {
        this.el.safetyBadge.style.display = 'flex';
        this.el.safetyText.textContent = 'KillSwitch Active';
      } else {
        this.el.safetyBadge.style.display = 'none';
      }
    } catch (e) { /* silent */ }
  },

  /** Poll full status */
  async pollStatus() {
    try {
      const data = await API.status();
      App.emit('statusUpdate', data);
      this.updateStatusBadge();
    } catch (e) { /* silent */ }
  },

  /** Update status badge */
  updateStatusBadge() {
    if (this.state.tradingMode === 'live') {
      this.el.botStatus.style.borderColor = 'var(--neon-green)';
      this.el.botStatus.querySelector('.dot').style.background = 'var(--neon-green)';
      this.el.statusText.textContent = 'LIVE';
    } else if (this.state.tradingMode === 'paper') {
      this.el.botStatus.style.borderColor = 'var(--neon-blue)';
      this.el.botStatus.querySelector('.dot').style.background = 'var(--neon-blue)';
      this.el.statusText.textContent = this.state.isPaused ? 'Paused' : 'Paper Trading';
    } else {
      this.el.botStatus.style.borderColor = 'var(--neon-yellow)';
      this.el.botStatus.querySelector('.dot').style.background = 'var(--neon-yellow)';
      this.el.statusText.textContent = this.state.tradingMode || 'Idle';
    }
  },

  // ── Toast Notifications ──
  toast(message, type = 'info') {
    const container = this.el.toastContainer;
    if (!container) return;

    const emojis = { success: '✅', error: '❌', info: '📡', warn: '⚠️' };
    const colors = { success: 'var(--neon-green)', error: 'var(--neon-red)', info: 'var(--neon-blue)', warn: 'var(--neon-yellow)' };

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.style.cssText = `border-color:${colors[type]};animation:slideIn 0.3s ease;`;
    toast.innerHTML = `<span>${emojis[type] || '⚡'}</span><span>${message}</span>`;
    container.appendChild(toast);

    // Auto-dismiss
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);

    // Save to notification history
    const notif = { id: Date.now(), message, type, time: new Date().toLocaleTimeString(), read: false };
    this.state.notifications.unshift(notif);
    if (this.state.notifications.length > 100) this.state.notifications.length = 100;
    if (!notif.read) this.state.unreadNotifications++;
    localStorage.setItem('nt_notifications', JSON.stringify(this.state.notifications));
    this.renderNotifications();
  },

  /** Toggle notification dropdown */
  toggleNotifications() {
    const dd = this.el.notificationDropdown;
    dd.style.display = dd.style.display === 'flex' ? 'none' : 'flex';
    if (dd.style.display === 'flex') this.markNotificationsRead();
  },

  /** Mark all notifications read */
  markNotificationsRead() {
    this.state.unreadNotifications = 0;
    this.state.notifications.forEach(n => n.read = true);
    localStorage.setItem('nt_notifications', JSON.stringify(this.state.notifications));
    this.renderNotifications();
  },

  /** Clear all notifications */
  clearNotifications() {
    this.state.notifications = [];
    this.state.unreadNotifications = 0;
    localStorage.setItem('nt_notifications', JSON.stringify([]));
    this.renderNotifications();
  },

  /** Render notification UI */
  renderNotifications() {
    const badge = this.el.notificationBadge;
    const list = this.el.notificationList;

    if (this.state.unreadNotifications > 0) {
      badge.style.display = 'block';
      badge.textContent = this.state.unreadNotifications > 99 ? '99+' : this.state.unreadNotifications;
    } else {
      badge.style.display = 'none';
    }

    if (list) {
      if (this.state.notifications.length === 0) {
        list.innerHTML = '<div style="color:var(--text-secondary);text-align:center;padding:20px">No notifications</div>';
      } else {
        list.innerHTML = this.state.notifications.slice(0, 20).map(n => `
          <div style="padding:6px 8px;border-left:2px solid var(--neon-${n.type === 'error' ? 'red' : n.type === 'success' ? 'green' : 'blue'});font-size:11px;margin-bottom:4px">
            <span style="color:var(--text-secondary)">${n.time}</span> ${n.message}
          </div>
        `).join('');
      }
    }
  },

  // ── Event System ──
  _listeners: {},

  on(event, fn) {
    (this._listeners[event] = this._listeners[event] || []).push(fn);
    return this;
  },

  off(event, fn) {
    const ls = this._listeners[event];
    if (ls) this._listeners[event] = ls.filter(f => f !== fn);
    return this;
  },

  emit(event, data) {
    (this._listeners[event] || []).forEach(fn => fn(data));
    // Also dispatch DOM event for decoupled modules
    document.dispatchEvent(new CustomEvent(`nt:${event}`, { detail: data }));
  },
};

// Shorthand
const byId = (id) => document.getElementById(id);

// Boot when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());
