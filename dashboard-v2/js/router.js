/**
 * router.js v3.2 — SPA router, global state, WebSocket, event bus
 */
const byId = (id) => document.getElementById(id);

const App = {
  state: {
    activeTab: 'dashboard', activeTicker: 'BTC-USD',
    tickers: [], tickerPrices: {},
    tradingMode: 'live', isPaused: false,
    speed: 0.2, riskMode: 'aggressive',
    ws: null, reconnectTimer: null, reconnectAttempts: 0,
    notifications: JSON.parse(localStorage.getItem('nt_notif_v2') || '[]'),
    unreadNotifications: 0,
  },
  el: {},

  // ── BOOT ──
  async init() {
    // Calculate unread on boot
    this.state.unreadNotifications = this.state.notifications.filter(n => !n.read).length;

    this.cacheDOM();
    this.bindEvents();
    this.initNav();
    await this.loadInitState();
    this.connectWS();
    this.startPolling();
    this.renderNotifications();
    if (typeof lucide !== 'undefined' && lucide?.createIcons) {
      try { lucide.createIcons(); } catch(e) {}
    }
    this.emit('ready');

    // Restore tab from URL hash
    const hash = location.hash.replace('#', '');
    if (hash && hash !== 'dashboard') {
      const tabId = 'tab-' + hash;
      if (byId(tabId)) this.switchTab(tabId);
    }

    // Track keyboard user for enhanced focus styles
    let isKeyboard = false;
    document.addEventListener('keydown', () => { if (!isKeyboard) { isKeyboard = true; document.body.classList.add('keyboard-nav'); } });
    document.addEventListener('mousedown', () => { if (isKeyboard) { isKeyboard = false; document.body.classList.remove('keyboard-nav'); } });
    document.addEventListener('touchstart', () => { if (isKeyboard) { isKeyboard = false; document.body.classList.remove('keyboard-nav'); } });
  },

  cacheDOM() {
    this.el = {
      statusText: byId('status-text'), botStatus: byId('bot-status'),
      safetyBadge: byId('safety-badge'), safetyText: byId('safety-text'),
      equity: byId('val-equity'), balance: byId('val-balance'),
      unrealizedPnl: byId('val-unrealized-pnl'),
      winrate: byId('val-winrate'), tradeCount: byId('val-trade-count'),
      totalPnl: byId('val-total-pnl'), totalPnlPct: byId('val-total-pnl-percent'),
      tickerPrice: byId('ticker-price'), tickerChange: byId('ticker-change'),
      tickerTitle: byId('chart-ticker-title'),
      probValue: byId('prob-value'), probGauge: byId('prob-gauge'),
      evValue: byId('val-ev'), rrValue: byId('val-rr'),
      kellyValue: byId('val-kelly'), sigStrength: byId('val-sig-strength'),
      viabilityBadge: byId('viability-badge'),
      positionDetails: byId('position-details-container'),
      tradeLog: byId('recent-trades-list'),
      weightsContainer: byId('weights-container'),
      tickerSwitcher: byId('ticker-switcher-bar'),
      simProgress: byId('sim-progress-container'),
      simProgressBar: byId('sim-progress-bar'),
      simProgressLabel: byId('sim-progress-label'),
      notificationBell: byId('notification-bell-btn'),
      notificationBadge: byId('notification-badge'),
      notificationDropdown: byId('notification-dropdown'),
      notificationList: byId('notification-list'),
      navDrawer: byId('nav-drawer'),
      navOverlay: byId('nav-drawer-overlay'),
    };
  },

  bindEvents() {
    byId('play-pause-btn')?.addEventListener('click', () => this.togglePause());
    byId('reset-btn')?.addEventListener('click', () => this.resetSim());
    byId('speed-slider')?.addEventListener('input', (e) => {
      this.state.speed = parseFloat(e.target.value);
      const l = byId('speed-label'); if (l) l.textContent = this.state.speed.toFixed(2) + 's';
      this.emit('speed', this.state.speed);
    });
    byId('risk-mode-select')?.addEventListener('change', (e) => this.setRiskMode(e.target.value));
    byId('open-drawer-btn')?.addEventListener('click', () => this.openDrawer());
    byId('close-drawer-btn')?.addEventListener('click', () => this.closeDrawer());

    // Close drawer on Escape key within drawer
    this.el.navDrawer?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeDrawer();
    });

    this.el.navOverlay?.addEventListener('click', () => this.closeDrawer());
    this.el.notificationBell?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleNotifications();
    });
    byId('clear-notifications-btn')?.addEventListener('click', () => this.clearNotifications());
    byId('btn-dev-toggle')?.addEventListener('click', () => {
      document.body.classList.toggle('debug');
      localStorage.setItem('nt_debug', document.body.classList.contains('debug') ? '1' : '0');
      this.toast(document.body.classList.contains('debug') ? 'Debug ON' : 'Debug OFF', 'info');
    });
    // Restore debug mode from localStorage
    if (localStorage.getItem('nt_debug') === '1') document.body.classList.add('debug');

    // Persist dark mode (still dark by default, but saves UI state)
    if (localStorage.getItem('nt_dark_mode') === '0') {
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      localStorage.setItem('nt_dark_mode', '1');
      document.documentElement.setAttribute('data-theme', 'dark');
    }
    // Listen for theme changes
    document.addEventListener('nt:themeChange', (e) => {
      const mode = e.detail?.dark ? '1' : '0';
      localStorage.setItem('nt_dark_mode', mode);
    });

    // Touch gesture support (swipe between tabs)
    this.initTouchGestures();

    // Keyboard navigation
    this.initKeyboardNav();

    // Close dropdown on outside click (use capture phase to handle properly)
    document.addEventListener('click', (e) => {
      if (this.el.notificationDropdown?.style.display === 'flex' &&
          !e.target.closest('.notification-dropdown-container')) {
        this.closeNotifications();
      }
    }, { capture: true });

    // Handle orientation changes: recalculate layout
    window.addEventListener('orientationchange', () => {
      setTimeout(() => {
        document.dispatchEvent(new CustomEvent('nt:resize'));
      }, 300);
    });

    // Prevent accidental long-press context menu on mobile
    document.querySelector('.dashboard-container')?.addEventListener('touchstart', (e) => {
      const target = e.target;
      if (target && (target.closest('button') || target.closest('.kpi-card') || target.closest('.chart-container'))) {
        // Allow long-press on actionable elements to proceed
        return;
      }
    }, { passive: true });
  },

  initNav() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const tid = tab.dataset.tab;
        if (tid) { this.switchTab(tid); this.closeDrawer(); }
      });
    });
  },

  switchTab(tabId) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.nav-tab[data-tab="${tabId}"]`)?.classList.add('active');
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const content = byId(tabId);
    if (content) {
      content.classList.add('active');
      this.state.activeTab = tabId.replace('tab-', '');
      history.replaceState(null, '', '#' + this.state.activeTab);
      this.emit('tabChange', this.state.activeTab);
      // Reinitialize icons in the newly visible tab
      try { if (typeof lucide !== 'undefined' && lucide?.createIcons) lucide.createIcons(); } catch(e) {}
    }
  },

  async togglePause() {
    this.state.isPaused = !this.state.isPaused;
    const icon = document.querySelector('#play-pause-btn i');
    const text = byId('play-pause-text');
    if (icon) icon.setAttribute('data-lucide', this.state.isPaused ? 'play' : 'pause');
    if (text) text.textContent = this.state.isPaused ? 'Play' : 'Pause';
    try { if (typeof lucide !== 'undefined' && lucide?.createIcons) lucide.createIcons(); } catch(e) {}
    try { await API.control(this.state.isPaused ? 'pause' : 'resume'); } catch(e) {}
  },

  async resetSim() {
    if (!confirm('Reset simulation? This clears all trade history.')) return;
    try { await API.control('reset'); this.toast('Simulation reset', 'info'); }
    catch(e) { this.toast('Reset failed: ' + e.message, 'error'); }
  },

  async setRiskMode(mode) {
    try { await API.setRiskMode(mode); this.state.riskMode = mode; this.toast('Risk: ' + mode, 'success'); }
    catch(e) { this.toast('Risk mode change failed', 'error'); }
  },

  openDrawer() {
    if (this.el.navDrawer) {
      this.el.navDrawer.style.left = '0';
      this.el.navDrawer.setAttribute('aria-hidden', 'false');
      // Focus trap: move focus into drawer
      setTimeout(() => {
        const firstTab = this.el.navDrawer.querySelector('.nav-tab');
        if (firstTab) firstTab.focus();
      }, 100);
    }
    if (this.el.navOverlay) this.el.navOverlay.style.display = 'block';
    byId('open-drawer-btn')?.setAttribute('aria-expanded', 'true');
    // Prevent body scroll when drawer open
    document.body.style.overflow = 'hidden';
  },

  closeDrawer() {
    if (this.el.navDrawer) {
      this.el.navDrawer.style.left = '-280px';
      this.el.navDrawer.setAttribute('aria-hidden', 'true');
      // Restore focus to hamburger button
      byId('open-drawer-btn')?.focus();
    }
    if (this.el.navOverlay) this.el.navOverlay.style.display = 'none';
    byId('open-drawer-btn')?.setAttribute('aria-expanded', 'false');
    // Restore body scroll
    document.body.style.overflow = '';
  },

  closeNotifications() {
    if (this.el.notificationDropdown) this.el.notificationDropdown.style.display = 'none';
    if (this.el.notificationBell) this.el.notificationBell.setAttribute('aria-expanded', 'false');
  },

  // ── Touch Gestures ──
  initTouchGestures() {
    const tabOrder = ['tab-dashboard', 'tab-neural', 'tab-assets', 'tab-strategy', 'tab-llm', 'tab-agents', 'tab-settings', 'tab-optimizations', 'tab-architecture', 'tab-logs'];
    let touchStartX = 0;
    let touchStartY = 0;
    const main = document.querySelector('main');
    if (!main) return;

    main.addEventListener('touchstart', (e) => {
      if (e.target.closest('.controls-bar') || e.target.closest('#nav-drawer') ||
          e.target.closest('.notification-dropdown-container') || e.target.closest('#toast-container') ||
          e.target.closest('select') || e.target.closest('input') || e.target.closest('textarea') ||
          e.target.closest('button') || e.target.closest('.ticker-tab')) {
        touchStartX = 0; return;
      }
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
    }, { passive: true });

    main.addEventListener('touchend', (e) => {
      if (touchStartX === 0) return;
      const diffX = e.changedTouches[0].clientX - touchStartX;
      const diffY = e.changedTouches[0].clientY - touchStartY;
      touchStartX = 0;

      // Require horizontal swipe > 60px and minimal vertical drift
      if (Math.abs(diffX) < 60 || Math.abs(diffY) > Math.abs(diffX) * 0.5) return;

      const currentIdx = tabOrder.indexOf(this.state.activeTab ? 'tab-' + this.state.activeTab : 'tab-dashboard');
      if (currentIdx === -1) return;

      let nextIdx;
      if (diffX < 0) {
        // Swipe left → next tab
        nextIdx = Math.min(currentIdx + 1, tabOrder.length - 1);
      } else {
        // Swipe right → previous tab
        nextIdx = Math.max(currentIdx - 1, 0);
      }

      if (nextIdx !== currentIdx) {
        this.switchTab(tabOrder[nextIdx]);
      }
    }, { passive: true });
  },

  // ── Keyboard Navigation ──
  initKeyboardNav() {
    const tabKeys = {
      '1': 'tab-dashboard', '2': 'tab-neural', '3': 'tab-assets',
      '4': 'tab-strategy', '5': 'tab-llm', '6': 'tab-agents',
      '7': 'tab-settings', '8': 'tab-optimizations', '9': 'tab-architecture',
      '0': 'tab-logs',
    };

    document.addEventListener('keydown', (e) => {
      // Escape: close drawer or notifications
      if (e.key === 'Escape') {
        if (this.el.navDrawer?.style.left === '0px' || this.el.navDrawer?.style.left === '0') {
          this.closeDrawer();
          e.preventDefault();
          return;
        }
        if (this.el.notificationDropdown?.style.display === 'flex') {
          this.closeNotifications();
          e.preventDefault();
          return;
        }
        return;
      }

      // Ctrl+[1-9,0] to switch tabs (also Meta for Mac)
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
        const tabId = tabKeys[e.key];
        if (tabId && byId(tabId)) {
          e.preventDefault();
          this.switchTab(tabId);
        }
      }

      // Arrow up/down within drawer: cycle nav items
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const drawer = this.el.navDrawer;
        if (drawer?.style.left === '0px' || drawer?.style.left === '0') {
          const tabs = drawer.querySelectorAll('.nav-tab');
          const activeIdx = Array.from(tabs).findIndex(t => t === document.activeElement);
          if (activeIdx >= 0) {
            e.preventDefault();
            const next = e.key === 'ArrowDown'
              ? (activeIdx + 1) % tabs.length
              : (activeIdx - 1 + tabs.length) % tabs.length;
            tabs[next].focus();
          }
        }
      }
    });
  },

  async loadInitState() {
    try {
      const data = await API.initState();
      this.state.tickers = data.tickers || [];
      this.state.tickerPrices = data.ticker_prices || {};
      this.state.tradingMode = data.trading_mode || 'live';
      this.state.riskMode = data.risk_mode || 'aggressive';
      this.state.activeTicker = this.state.tickers[0] || 'BTC-USD';

      const rs = byId('risk-mode-select'); if (rs) rs.value = this.state.riskMode;
      this.updateStatusBadge();

      if (this.state.tickerPrices[this.state.activeTicker] && this.el.tickerPrice) {
        this.el.tickerPrice.textContent = '$' + Number(this.state.tickerPrices[this.state.activeTicker]).toFixed(2);
      }
      this.renderTickerSwitcher();
      // Fetch supplemental position data first, then emit initState with positions
      const posData = await this.fetchPositions();
      if (posData) {
        data.positions = posData;
      }
      this.emit('initState', data);
    } catch(e) {
      console.error('Init failed:', e);
      this.toast('Failed to load initial state', 'error');
      // Show connection error in status bar
      if (this.el.statusText) this.el.statusText.textContent = 'Connection Error';
      if (this.el.botStatus) {
        this.el.botStatus.style.borderColor = 'var(--neon-red)';
        const dot = this.el.botStatus.querySelector('.dot');
        if (dot) dot.style.background = 'var(--neon-red)';
      }
    }
  },

  renderTickerSwitcher() {
    const c = this.el.tickerSwitcher; if (!c) return;
    c.innerHTML = '';

    (this.state.tickers || []).forEach(t => {
      const btn = document.createElement('button');
      btn.className = 'ticker-tab'; btn.dataset.ticker = t;
      const price = this.state.tickerPrices?.[t] ? '$' + Number(this.state.tickerPrices[t]).toFixed(2) : '--';
      btn.innerHTML = `<span class="ticker-tab-name">${t}</span><span class="ticker-tab-price" id="tab-price-${t}">${price}</span>`;
      btn.addEventListener('click', () => this.selectTicker(t));
      c.appendChild(btn);
    });

    const pb = document.createElement('button');
    pb.id = 'tab-portfolio'; pb.className = 'ticker-tab';
    pb.innerHTML = '<span class="ticker-tab-name" style="color:var(--neon-purple);font-weight:700">Portfolio</span><span class="ticker-tab-price" id="tab-portfolio-equity">$0.00</span>';
    pb.addEventListener('click', () => this.selectTicker('portfolio'));
    c.appendChild(pb);

    // Re-init icons after DOM injection
    try { if (typeof lucide !== 'undefined' && lucide?.createIcons) lucide.createIcons(); } catch(e) {}
    this.selectTicker(this.state.activeTicker || (this.state.tickers && this.state.tickers[0]) || 'BTC-USD');
  },

  selectTicker(ticker) {
    this.state.activeTicker = ticker;
    document.querySelectorAll('.ticker-tab').forEach(b => {
      b.classList.toggle('active-ticker',
        b.dataset.ticker === ticker || (ticker === 'portfolio' && b.id === 'tab-portfolio'));
    });
    if (this.el.tickerTitle) {
      this.el.tickerTitle.textContent = ticker === 'portfolio' ? '📊 Portfolio Overview' : ticker;
    }
    this.emit('tickerChange', ticker);
  },

  updateStatusBadge() {
    const mode = this.state.tradingMode;
    const badge = this.el.botStatus;
    if (!badge) return;
    const dot = badge.querySelector('.dot');
    if (mode === 'live') {
      badge.style.borderColor = 'var(--neon-green)';
      if (dot) dot.style.background = 'var(--neon-green)';
      this.el.statusText.textContent = 'LIVE';
    } else if (mode === 'paper') {
      badge.style.borderColor = 'var(--neon-blue)';
      if (dot) dot.style.background = 'var(--neon-blue)';
      this.el.statusText.textContent = this.state.isPaused ? 'Paused' : 'Paper Trading';
    } else {
      badge.style.borderColor = 'var(--neon-yellow)';
      if (dot) dot.style.background = 'var(--neon-yellow)';
      this.el.statusText.textContent = mode || 'Idle';
    }
  },

  // ── WebSocket ──
  connectWS() {
    // Close any existing connection cleanly before opening a new one
    if (this.state.ws) {
      try {
        this.state.ws.onclose = null; // prevent reconnect trigger from old socket
        this.state.ws.close();
      } catch(e) {}
    }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    try {
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      this.state.ws = ws;

      ws.onopen = () => {
        this.el.botStatus?.classList.remove('stopped');
        this.el.statusText.textContent = this.state.tradingMode === 'live' ? 'LIVE' : 'Connected';
        this.state.reconnectAttempts = 0; // Reset on successful connection
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          this.emit('wsMessage', msg);
        } catch(e) {
          // Silently ignore malformed messages
          this.debug('WS parse error:', e);
        }
      };

      ws.onclose = () => {
        this.el.statusText.textContent = 'Disconnected';
        this.el.botStatus?.classList.add('stopped');
        // Exponential backoff with jitter for reconnection
        this.state.reconnectAttempts++;
        const delay = Math.min(30000, Math.pow(2, this.state.reconnectAttempts) * 1000) + Math.random() * 1000;
        this.debug('WS closed, reconnecting in ' + Math.round(delay) + 'ms (attempt ' + this.state.reconnectAttempts + ')');
        this.state.reconnectTimer = setTimeout(() => {
          // Clear stale polling timers if any
          if (this._safetyTimer) clearTimeout(this._safetyTimer);
          if (this._statusTimer) clearTimeout(this._statusTimer);
          this.connectWS();
        }, delay);
      };

      ws.onerror = (err) => {
        this.el.statusText.textContent = 'Connection Error';
        this.el.botStatus?.classList.add('stopped');
        this.debug('WS error:', err);
      };
    } catch(e) {
      this.debug('WS creation failed:', e);
      this.el.statusText.textContent = 'WS Error';
      this.el.botStatus?.classList.add('stopped');
    }
  },

  startPolling() {
    const safetyLoop = async () => {
      await this.pollSafety();
      this._safetyTimer = setTimeout(safetyLoop, 5000);
    };
    const statusLoop = async () => {
      await this.pollStatus();
      this._statusTimer = setTimeout(statusLoop, 10000);
    };
    safetyLoop();
    statusLoop();
  },

  async pollSafety() {
    try {
      const data = await API.safetyStatus();
      if (data?.kill_switch?.tripped === true) {
        if (this.el.safetyBadge) {
          this.el.safetyBadge.style.display = 'flex';
          this.el.safetyBadge.setAttribute('role', 'alert');
        }
        if (this.el.safetyText) this.el.safetyText.textContent = 'KillSwitch Active';
      } else {
        if (this.el.safetyBadge) {
          this.el.safetyBadge.style.display = 'none';
          this.el.safetyBadge.removeAttribute('role');
        }
      }
    } catch(e) {}
  },

  async pollStatus() {
    try {
      const data = await API.status();
      // If status response doesn't include positions/trades, augment from separate endpoints
      const augmented = Object.assign({}, data);
      if (!data.positions) {
        try {
          const pos = await API.positions();
          if (pos && (Array.isArray(pos) ? pos.length : Object.keys(pos).length)) {
            augmented.positions = pos;
          }
        } catch(e2) { /* positions unavailable */ }
      }
      this.emit('statusUpdate', augmented);
      this.updateStatusBadge();
    } catch(e) {}
  },

  async fetchPositions() {
    try {
      const data = await API.positions();
      if (data && (Array.isArray(data) ? data.length : Object.keys(data).length)) {
        return data;
      }
    } catch(e) { /* positions may not be available yet */ }
    return null;
  },

  // ── Toast ──
  toast(message, type = 'info') {
    const container = byId('toast-container');
    if (!container) return;

    const emojis = { success: '✅', error: '❌', info: '📡', warn: '⚠️' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.animation = 'slideIn 0.3s ease';
    toast.setAttribute('role', 'status');
    toast.innerHTML = `<span aria-hidden="true">${emojis[type] || '⚡'}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);

    const notif = { id: Date.now(), message, type, time: new Date().toLocaleTimeString(), read: false };
    this.state.notifications.unshift(notif);
    if (this.state.notifications.length > 100) this.state.notifications.length = 100;
    this.state.unreadNotifications++;
    localStorage.setItem('nt_notif_v2', JSON.stringify(this.state.notifications));
    this.renderNotifications();
  },

  toggleNotifications() {
    const dd = this.el.notificationDropdown;
    const bell = this.el.notificationBell;
    if (!dd) return;
    const isOpen = dd.style.display === 'flex';
    dd.style.display = isOpen ? 'none' : 'flex';
    if (bell) bell.setAttribute('aria-expanded', String(!isOpen));
    if (!isOpen) {
      this.markNotificationsRead();
    }
  },

  markNotificationsRead() {
    this.state.unreadNotifications = 0;
    this.state.notifications.forEach(n => n.read = true);
    localStorage.setItem('nt_notif_v2', JSON.stringify(this.state.notifications));
    this.renderNotifications();
  },

  clearNotifications() {
    this.state.notifications = [];
    this.state.unreadNotifications = 0;
    localStorage.setItem('nt_notif_v2', '[]');
    this.renderNotifications();
  },

  renderNotifications() {
    const badge = this.el.notificationBadge;
    const list = this.el.notificationList;

    if (badge) {
      if (this.state.unreadNotifications > 0) {
        badge.style.display = 'block';
        badge.textContent = this.state.unreadNotifications > 99 ? '99+' : String(this.state.unreadNotifications);
      } else { badge.style.display = 'none'; }
    }

    if (list) {
      if (!this.state.notifications.length) {
        list.innerHTML = '<div style="color:var(--text-secondary);text-align:center;padding:20px;font-size:12px">No notifications yet</div>';
      } else {
        list.innerHTML = this.state.notifications.slice(0, 20).map(n => {
          const borderColor = n.type === 'error' ? 'var(--neon-red)' : n.type === 'success' ? 'var(--neon-green)' : n.type === 'warn' ? 'var(--neon-yellow)' : 'var(--neon-blue)';
          return `<div style="padding:6px 8px;border-left:2px solid ${borderColor};font-size:11px;margin-bottom:4px;background:rgba(255,255,255,0.02);border-radius:0 4px 4px 0">
            <span style="color:var(--text-muted);font-size:10px">${n.time}</span> ${n.message}
          </div>`;
        }).join('');
      }
    }
  },

  // ── Event Bus ──
  _listeners: {},
  on(event, fn) { (this._listeners[event] = this._listeners[event] || []).push(fn); return this; },
  off(event, fn) { const ls = this._listeners[event]; if (ls) this._listeners[event] = ls.filter(f => f !== fn); return this; },
  emit(event, data) {
    (this._listeners[event] || []).forEach(fn => { try { fn(data); } catch(e) { console.error('Event handler error:', event, e); } });
    document.dispatchEvent(new CustomEvent(`nt:${event}`, { detail: data }));
  },

  // ── Debounce utility ──
  _debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  },

  // ── Helpers ──
  debug(...args) { if (document.body.classList.contains('debug')) console.log('[NT]', ...args); },
};

// Helpers for other modules
function setInput(id, val) { const el = byId(id); if (el) el.value = val ?? ''; }
function setCheckbox(id, val) { const el = byId(id); if (el) el.checked = !!val; }
function getInput(id) { return byId(id)?.value || ''; }

// Form validation helpers
function validateInput(id, validator) {
  const el = byId(id);
  if (!el) return true;
  el.classList.remove('error', 'valid');
  const msg = el.parentElement?.querySelector('.validation-message');
  if (msg) msg.className = 'validation-message';
  const val = el.value.trim();
  const result = validator ? validator(val) : val.length > 0;
  if (result === true || result === '') {
    el.classList.add('valid');
    if (msg) msg.className = 'validation-message valid';
    return true;
  }
  el.classList.add('error');
  if (msg) {
    msg.className = 'validation-message error';
    msg.textContent = result || 'Invalid value';
  }
  return false;
}

function showEmptyState(container, { icon, title, desc, action } = {}) {
  if (!container) return;
  container.innerHTML = '<div class="empty-state" role="status">' +
    (icon ? '<div class="empty-state-icon" aria-hidden="true">' + icon + '</div>' : '') +
    (title ? '<div class="empty-state-title">' + title + '</div>' : '') +
    (desc ? '<div class="empty-state-desc">' + desc + '</div>' : '') +
    (action || '') +
    '</div>';
}

function showSkeleton(container, count = 3) {
  if (!container) return;
  container.innerHTML = '';
  for (let i = 0; i < count; i++) {
    const s = document.createElement('div');
    s.className = 'skeleton skeleton-text';
    s.style.width = (60 + Math.random() * 35) + '%';
    s.setAttribute('aria-hidden', 'true');
    container.appendChild(s);
  }
}

document.addEventListener('DOMContentLoaded', () => App.init());
