/**
 * dashboard.js v3.2 — Main dashboard tab: charts, KPIs, trade log, weights
 */
const Dashboard = {
  chart: null, weightsChart: null, chartSeries: {}, chartType: 'candles', chartData: [],
  _resizeTimer: null, _chartEl: null,

  init() {
    this._chartEl = byId('main-chart');
    this.initFreshness();
    try { this.initCharts(); } catch(e) { console.error('Chart init failed:', e); }
    document.addEventListener('nt:initState', (e) => this.onInitState(e.detail));
    document.addEventListener('nt:wsMessage', (e) => this.onWSMessage(e.detail));
    document.addEventListener('nt:tickerChange', (e) => this.onTickerChange(e.detail));
    document.addEventListener('nt:statusUpdate', (e) => this.onStatusUpdate(e.detail));

    document.querySelectorAll('.chart-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-type-btn').forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');
        this.chartType = btn.dataset.type;
        this.redrawChart();
      });
    });

    // Chart zoom reset
    byId('chart-reset-zoom')?.addEventListener('click', () => {
      if (this.chart && this.chartData?.length) {
        this.chart.timeScale().fitContent();
        App?.toast('Chart zoom reset', 'info');
      }
    });

    try { if (typeof lucide !== 'undefined' && lucide?.createIcons) lucide.createIcons(); } catch(e) {}
  },

  initFreshness() {
    ['chart','portfolio'].forEach(id => this.updateFreshness(id, null));
  },

  initCharts() {
    if (!this._chartEl || typeof LightweightCharts === 'undefined') return;

    // Debounced resize handler to prevent layout thrashing
    const doResize = () => {
      if (this.chart && this._chartEl?.clientWidth) {
        const w = this._chartEl.clientWidth;
        const h = this._chartEl.clientHeight || 420;
        if (w > 0 && h > 0) {
          this.chart.applyOptions({ width: w, height: h });
        }
      }
    };
    const debouncedResize = this._debounce(doResize, 200);
    window.addEventListener('resize', debouncedResize);

    document.addEventListener('nt:resize', () => {
      if (this._resizeTimer) clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(doResize, 200);
    });

    // Use ResizeObserver for reliable size tracking (if available)
    if (typeof ResizeObserver !== 'undefined') {
      this._chartResizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width, height } = entry.contentRect;
          if (this.chart && width > 0 && height > 0) {
            this.chart.applyOptions({ width: Math.round(width), height: Math.round(height) });
          }
        }
      });
      this._chartResizeObserver.observe(this._chartEl);
    }

    this.chart = LightweightCharts.createChart(this._chartEl, {
      width: this._chartEl.clientWidth || 800,
      height: this._chartEl.clientHeight || 420,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true },
      handleScroll: { vertTouchDrag: false }, // Prevent vertical scroll on touch
    });

    this.chartSeries.candles = this.chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#f43f5e',
      borderUpColor: '#10b981', borderDownColor: '#f43f5e',
      wickUpColor: '#10b981', wickDownColor: '#f43f5e',
      priceLineVisible: true,
      lastValueVisible: true,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    this.chartSeries.volume = this.chart.addHistogramSeries({
      color: 'rgba(59,130,246,0.25)', priceFormat: { type: 'volume' }, priceScaleId: '',
    });
    this.chart.priceScale('').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });

    // Doughnut chart for weights
    const wEl = byId('weights-chart');
    if (wEl && typeof Chart !== 'undefined') {
      const ctx = wEl.getContext('2d');
      try {
        this.weightsChart = new Chart(ctx, {
          type: 'doughnut',
          data: { labels: [], datasets: [{ data: [], backgroundColor: ['#3b82f6','#10b981','#f59e0b','#8b5cf6','#ec4899','#06b6d4','#f43f5e','#84cc16'] }] },
          options: {
            responsive: true, maintainAspectRatio: false, cutout: '65%',
            plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 10 }, padding: 12 } } },
          },
        });
      } catch(e) {
        console.error('Weights chart init failed:', e);
      }
    }
  },

  _debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  },

  redrawChart() {
    if (!this.chart || !this.chartSeries?.candles || !this.chartData?.length) return;
    if (this.chartType === 'line') {
      const flat = this.chartData.map(d => ({ time: d.time, open: d.close, high: d.close, low: d.close, close: d.close }));
      this.chartSeries.candles.setData(flat);
      this.chartSeries.candles.applyOptions({
        upColor: '#3b82f6', downColor: '#3b82f6', borderUpColor: '#3b82f6', borderDownColor: '#3b82f6',
        wickUpColor: '#3b82f6', wickDownColor: '#3b82f6',
      });
    } else {
      this.chartSeries.candles.applyOptions({
        upColor: '#10b981', downColor: '#f43f5e', borderUpColor: '#10b981', borderDownColor: '#f43f5e',
        wickUpColor: '#10b981', wickDownColor: '#f43f5e',
      });
      this.chartSeries.candles.setData(this.chartData);
    }
  },

  async onInitState(data) {
    this.updateKPIs(data);
    // Collect trades from multiple possible field names
    const trades = data.trades || data.recent_trades || data.trade_history || [];
    this.renderTrades(trades);
    // Render positions if present in init state
    if (data.positions) this.renderPositions(data.positions);
    if (App.state && App.state.activeTicker !== 'portfolio') this.loadHistory(App.state.activeTicker);
    this.fetchWeights();
  },

  async fetchWeights() {
    const c = byId('weights-container');
    if (c) {
      showSkeleton(c, 4);
    }
    try {
      const d = await API.weights();
      if (d?.weights) this.renderWeights(d.weights);
      else if (c) this.renderWeights(null);
    } catch(e) {
      if (c) {
        c.innerHTML = '<div class="retry-indicator"><span>⚠️ Weights unavailable</span><button class="retry-btn" onclick="Dashboard?.fetchWeights()">Retry</button></div>';
      }
    }
  },

  onWSMessage(msg) {
    if (msg.type === 'tick') this.onTick(msg);
    else if (msg.type === 'init_state' || msg.type === 'state') {
      // Handle nested data structures: msg.data could be the payload or msg.data.data
      const payload = msg.data ? (msg.data.data || msg.data) : msg;
      this.onInitState(payload);
    }
  },

  onTick(msg) {
    try {
      const data = msg.data || msg; if (!data) return;
      if (data.price != null) {
        const pe = byId('ticker-price');
        if (pe) pe.textContent = '$' + Number(data.price).toFixed(2);
        if (data.change_pct != null) {
          const cel = byId('ticker-change');
          if (cel) {
            cel.textContent = (data.change_pct >= 0 ? '+' : '') + Number(data.change_pct).toFixed(2) + '%';
            cel.style.color = data.change_pct >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
          }
        }
      }
      if (data.ticker && data.price != null) {
        const te = byId('tab-price-' + data.ticker);
        if (te) te.textContent = '$' + Number(data.price).toFixed(2);
      }
      if (data.price != null && this.chartSeries?.candles) {
        try {
          const ts = data.timestamp || Math.floor(Date.now()/1000);
          this.chartSeries.candles.update({
            time: ts,
            open: data.open || data.price,
            high: data.high || data.price,
            low: data.low || data.price,
            close: data.price
          });
        } catch(e) {
          this.chart?.timeScale()?.fitContent();
        }
      }
      // Update data freshness indicator
      this.updateFreshness('chart', data.timestamp);
      this.updateFreshness('portfolio', data.timestamp);
      this.updateKPIs(data);
      if (data.sim_progress != null) {
        const c = byId('sim-progress-container');
        const b = byId('sim-progress-bar');
        const l = byId('sim-progress-label');
        const pct = Math.round(data.sim_progress);
        if (data.sim_progress > 0 && data.sim_progress < 100) {
          if (c) { c.style.display = 'flex'; c.setAttribute('aria-valuenow', String(pct)); }
          if (b) b.style.width = pct + '%';
          if (l) l.textContent = pct + '%';
        } else if (c) { c.style.display = 'none'; }
      }
      // Accumulate positions from individual tick updates (WS sends one per tick)
      if (data.positions !== undefined) {
        if (typeof data.positions === 'object' && data.positions !== null && Object.keys(data.positions).length === 0) {
          // Empty object received — clear positions
          this._wsPositions = {};
          this.renderPositions([]);
        } else if (data.positions) {
          this._wsPositions = data.positions;
          this.renderPositions(data.positions);
        }
      } else if (data.position && data.ticker) {
        if (!this._wsPositions) this._wsPositions = {};
        if (data.position) {
          data.position.symbol = data.position.symbol || data.ticker;
          this._wsPositions[data.ticker] = data.position;
        } else {
          delete this._wsPositions[data.ticker];
        }
        this.renderPositions(this._wsPositions);
      }
    } catch(e) {
      if (document.body.classList.contains('debug')) console.warn('[NT] Tick render error:', e);
    }
  },

  updateKPIs(data) {
    try {
      if (data.equity != null) { const e = byId('val-equity'); if (e) e.textContent = '$' + Number(data.equity).toFixed(2); }
      if (data.balance != null) { const e = byId('val-balance'); if (e) e.textContent = '$' + Number(data.balance).toFixed(2); }
      if (data.unrealized_pnl != null) {
        const p = Number(data.unrealized_pnl); const e = byId('val-unrealized-pnl');
        if (e) { e.textContent = 'Active Trade PnL: $' + p.toFixed(2); e.style.color = p >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'; }
      }
      if (data.winrate != null) { 
        const wr = Number(data.winrate);
        // Normalize: if already > 1, assume it's already percentage value (e.g. 75)
        const e = byId('val-winrate'); 
        if (e) e.textContent = (wr > 1 ? wr : wr * 100).toFixed(1) + '%'; 
      }
      const tc = data.today_trade_count ?? data.trade_count ?? (data.closed_trades != null ? Number(data.closed_trades) : Array.isArray(data.trades) ? data.trades.length : undefined);
      if (tc != null) { const e = byId('val-trade-count'); if (e) e.textContent = tc + ' trades completed'; }
      if (data.total_pnl != null) {
        const p = Number(data.total_pnl); const e = byId('val-total-pnl'); if (e) { e.textContent = '$' + p.toFixed(2); e.style.color = p >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'; }
        let pct = data.total_pnl_pct;
        // Compute total_pnl_pct from initial_balance if not provided (div by initial_balance not current)
        if (pct == null && data.initial_balance != null && Number(data.initial_balance) > 0) {
          pct = p / Number(data.initial_balance);
        } else if (pct == null && data.balance != null && Number(data.balance) > 0) {
          pct = p / Number(data.balance);
        } else if (pct == null && data.equity != null && Number(data.equity) > 0) {
          pct = p / Number(data.equity);
        }
        const e2 = byId('val-total-pnl-percent');
        if (e2 && pct != null) { e2.textContent = (pct>=0?'+':'') + Number(pct).toFixed(2)+'%'; e2.style.color = pct>=0?'var(--neon-green)':'var(--neon-red)'; }
        else if (e2 && pct == null) { e2.textContent = ''; }
      }
      const pe = byId('tab-portfolio-equity'); if (pe && data.equity != null) pe.textContent = '$' + Number(data.equity).toFixed(2);
    } catch(e) {}
  },

  async loadHistory(ticker) {
    if (ticker === 'portfolio' || !this.chartSeries?.candles) return;

    // Show loading state in chart data info
    const infoEl = byId('chart-data-info');
    if (infoEl) {
      infoEl.textContent = '⏳ Loading ' + ticker + '...';
      infoEl.style.display = 'inline';
    }

    try {
      const data = await API.history(ticker);
      const rows = Array.isArray(data) ? data : (data?.candles || data?.data || []);
      if (!rows?.length) {
        if (infoEl) infoEl.textContent = '⚠️ No data for ' + ticker;
        return;
      }

      const toTime = ts => {
        if (typeof ts === 'number') return ts < 1e12 ? ts : ts / 1000;
        if (typeof ts === 'string') { const d = new Date(ts); return isNaN(d.getTime()) ? null : Math.floor(d.getTime()/1000); }
        return null;
      };

      const cd = [];
      for (const c of rows) {
        const t = toTime(c.timestamp ?? c.time); if (t == null) continue;
        const o = Number(c.open ?? c.close ?? c.price ?? 0);
        const h = Number(c.high ?? c.close ?? c.price ?? 0);
        const l = Number(c.low ?? c.close ?? c.price ?? 0);
        const cl = Number(c.close ?? c.price ?? 0);
        if (isNaN(o) || isNaN(cl)) continue;
        cd.push({ time: t, open: o, high: h, low: l, close: cl });
      }
      if (!cd.length) {
        if (infoEl) infoEl.textContent = '⚠️ No valid candles for ' + ticker;
        return;
      }
      cd.sort((a,b) => a.time - b.time);

      this.chartData = cd;
      if (infoEl) infoEl.textContent = '📊 ' + cd.length + ' candles loaded';
      this.redrawChart();
      // Fit content after loading new data
      if (this.chart) this.chart.timeScale().fitContent();
    } catch(e) {
      console.error('History load failed:', e);
      if (infoEl) infoEl.textContent = '❌ Chart error';
      // Show retry option above chart, not replacing the chart container
      const freshEl = byId('freshness-chart');
      if (freshEl) {
        freshEl.className = 'data-freshness stale';
        const t = freshEl.querySelector('.freshness-text');
        if (t) t.textContent = 'Chart error';
      }
      // Add retry button next to chart info
      const chartInfo = byId('chart-data-info');
      if (chartInfo && !byId('chart-retry-btn')) {
        const retryBtn = document.createElement('button');
        retryBtn.id = 'chart-retry-btn';
        retryBtn.className = 'btn btn-sm';
        retryBtn.textContent = '🔄 Retry';
        retryBtn.style.marginLeft = '8px';
        retryBtn.addEventListener('click', function() { Dashboard.loadHistory(App.state.activeTicker); });
        chartInfo.parentNode.appendChild(retryBtn);
      }
    }
  },

  onTickerChange(ticker) {
    if (ticker !== 'portfolio') this.loadHistory(ticker);
  },

  async onStatusUpdate(data) {
    this.updateKPIs(data);
    if (data.trades) this.renderTrades(data.trades);
    if (data.positions) this.renderPositions(data.positions);
    if (data.weights) this.renderWeights(data.weights);
    if (data.probability) this.renderProbability(data.probability);
    // Only fetch weights if not already present in data and not recently fetched
    if (!data.weights && (!this._lastWeightsFetch || Date.now() - this._lastWeightsFetch > 30000)) {
      this._lastWeightsFetch = Date.now();
      this.fetchWeights();
    }
  },

  renderTrades(trades) {
    const tbody = byId('recent-trades-list'); if (!tbody) return;
    if (!trades?.length) {
      tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state" style="padding:30px 20px"><div class="empty-state-icon" style="font-size:36px" aria-hidden="true">📊</div><div class="empty-state-title">No trades yet</div><div class="empty-state-desc">The bot is collecting data and analyzing market conditions. Trades will appear here once executed.</div></div></td></tr>';
      return;
    }
    // Limit trades to avoid huge DOM operations
    const tradeSlice = trades.slice(0, 50);
    tbody.innerHTML = tradeSlice.map(t => {
      const rawTs = t.entry_time || t.exit_time || t.timestamp || t.time;
      let date = '—';
      if (rawTs != null) {
        let ts = Number(rawTs);
        if (String(rawTs).length >= 13) ts = Math.floor(ts / 1000); // ms to s
        if (ts > 0 && isFinite(ts)) date = new Date(ts * 1000).toLocaleDateString();
      }
      const dir = t.direction || '—';
      const dirColor = dir === 'long' ? 'var(--neon-green)' : dir === 'short' ? 'var(--neon-red)' : 'var(--text-secondary)';
      const pnl = Number(t.pnl || 0);
      const pnlPct = t.pnl_pct != null ? Number(t.pnl_pct) : null;
      let pnlStr;
      if (pnlPct != null) {
        pnlStr = (pnl>=0?'+':'') + '$' + pnl.toFixed(2) + ' (' + (pnlPct>=0?'+':'') + pnlPct.toFixed(2) + '%)';
      } else {
        pnlStr = (pnl>=0?'+':'') + '$' + pnl.toFixed(2);
      }
      return `<tr>
        <td style="color:var(--text-muted);font-size:10px">${date}</td>
        <td style="font-weight:600">${t.symbol || t.ticker || '—'}</td>
        <td style="color:${dirColor};font-weight:600">${dir.toUpperCase()}</td>
        <td style="font-family:var(--font-mono)">$${Number(t.entry_price||0).toFixed(2)}</td>
        <td style="font-family:var(--font-mono)">$${Number(t.exit_price||0).toFixed(2)}</td>
        <td class="${pnl>=0?'pnl-up':'pnl-down'}" style="font-weight:600;font-family:var(--font-mono)">${pnlStr}</td>
      </tr>`;
    }).join('');
  },

  renderWeights(weights) {
    const c = byId('weights-container'); if (!c) return;
    if (!weights || !Object.keys(weights).length) {
      c.innerHTML = '<div class="empty-state" style="padding:20px 10px" role="status"><div class="empty-state-icon" style="font-size:24px" aria-hidden="true">⚖️</div><div class="empty-state-title">No weights</div><div class="empty-state-desc" style="font-size:10px">Strategy weights appear once trading begins.</div></div>';
    } else {
      const entries = Object.entries(weights);
      const wValues = Object.values(weights).filter(function(v) { return typeof v === 'number' && isFinite(v); });
      if (!wValues.length) {
        c.innerHTML = '<div class="empty-state" style="padding:20px 10px" role="status"><div class="empty-state-icon" style="font-size:24px" aria-hidden="true">⚖️</div><div class="empty-state-title">No valid weight values</div></div>';
        return;
      }
      const maxW = Math.max.apply(null, wValues.concat([0.01]));
      c.innerHTML = entries.map(([n,w]) => {
        const pct = (w / maxW * 100).toFixed(0);
        const opacity = (0.4 + (w / maxW * 0.6)).toFixed(1);
        return `<div class="weight-bar">
          <span class="weight-label">${n}</span>
          <div class="weight-fill" style="width:${pct}%;opacity:${opacity}"></div>
          <span class="weight-val">${(w*100).toFixed(1)}%</span>
        </div>`;
      }).join('');
    }
    if (this.weightsChart) {
      this.weightsChart.data.labels = Object.keys(weights||{});
      this.weightsChart.data.datasets[0].data = Object.values(weights||{});
      this.weightsChart.update('none'); // 'none' avoids animation for rapid updates
    }
  },

  renderPositions(positions) {
    const c = byId('position-details-container'); if (!c) return;
    // Handle null, undefined, empty array, empty object
    if (positions == null || (Array.isArray(positions) && positions.length === 0) || (typeof positions === 'object' && !Array.isArray(positions) && Object.keys(positions).length === 0)) {
      c.innerHTML = '<span style="color:var(--text-muted)">No active positions</span>'; return;
    }
    if (!Array.isArray(positions) && typeof positions === 'object' && positions.entry_price) {
      return this.renderPositions([positions]);
    }
    let pa = positions;
    if (!Array.isArray(positions) && typeof positions === 'object') {
      pa = Object.entries(positions).map(function(e) {
        var key = e[0], p = e[1];
        // Skip numeric/array-like keys (server may return indexed object)
        if (p && typeof p === 'object') {
          if (!p.symbol && isNaN(Number(key))) p.symbol = key;
          return p;
        }
        return null;
      }).filter(Boolean);
    }
    if (!pa || pa.length === 0) { c.innerHTML = '<span style="color:var(--text-muted)">No active positions</span>'; return; }
    c.innerHTML = pa.map(function(pos) {
      var dir = pos.direction || 'long';
      var dc = dir === 'long' ? 'var(--neon-green)' : 'var(--neon-red)';
      var pnl = Number(pos.unrealized_pnl || 0);
      var sym = pos.symbol || '\u2014';
      return '<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:4px;padding-bottom:4px;border-bottom:1px solid var(--border-subtle)">' +
        '<span style="color:var(--text-muted);font-weight:600;font-size:11px;min-width:55px">' + sym + '</span>' +
        '<span style="color:' + dc + ';font-weight:700;font-size:12px">' + dir.toUpperCase() + '</span>' +
        '<span style="font-family:var(--font-mono);font-size:11px">Entry: <b>$' + Number(pos.entry_price||0).toFixed(2) + '</b></span>' +
        '<span style="font-family:var(--font-mono);font-size:11px">Size: <b>' + Number(pos.size||pos.quantity||0).toFixed(6) + '</b></span>' +
        '<span style="font-family:var(--font-mono);font-size:11px">PnL: <b style="color:' + (pnl>=0?'var(--neon-green)':'var(--neon-red)') + '">$' + pnl.toFixed(2) + '</b></span>' +
      '</div>';
    }).join('');
  },

  updateFreshness(id, timestamp) {
    const el = byId('freshness-' + id);
    if (!el) return;
    const dot = el.querySelector('.freshness-dot');
    const text = el.querySelector('.freshness-text');
    if (!timestamp) {
      el.className = 'data-freshness loading';
      if (text) text.textContent = 'Waiting for data';
      return;
    }
    const age = Date.now() - (timestamp < 1e12 ? timestamp * 1000 : timestamp);
    el.className = 'data-freshness';
    if (age < 5000) {
      if (text) text.textContent = 'Live';
    } else if (age < 60000) {
      if (text) text.textContent = Math.round(age/1000) + 's ago';
    } else if (age < 3600000) {
      if (text) text.textContent = Math.round(age/60000) + 'm ago';
    } else {
      el.classList.add('stale');
      if (text) text.textContent = 'Stale';
    }
  },

  renderProbability(prob) {
    if (!prob || typeof prob !== 'object') return;
    if (prob.probability != null) {
      const p = Number(prob.probability);
      byId('prob-value').textContent = (p*100).toFixed(1)+'%';
      byId('prob-gauge').style.width = (p*100).toFixed(0)+'%';
    }
    if (prob.ev != null) byId('val-ev').textContent = '$'+Number(prob.ev).toFixed(2);
    if (prob.risk_reward != null) byId('val-rr').textContent = Number(prob.risk_reward).toFixed(2);
    if (prob.kelly_fraction != null) byId('val-kelly').textContent = (Number(prob.kelly_fraction)*100).toFixed(1)+'%';
    if (prob.signal_strength != null) byId('val-sig-strength').textContent = (Number(prob.signal_strength)*100).toFixed(1)+'%';
    if (prob.viable != null) {
      const b = byId('viability-badge');
      b.textContent = prob.viable ? '✅ VIABLE' : '🛑 NO TRADE';
      b.style.background = prob.viable ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)';
      b.style.color = prob.viable ? 'var(--neon-green)' : 'var(--neon-red)';
    }
  },
};

document.addEventListener('DOMContentLoaded', () => { Dashboard.init(); try { if (typeof lucide !== 'undefined' && lucide?.createIcons) lucide.createIcons(); } catch(e) {} });
