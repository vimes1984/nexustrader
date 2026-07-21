/**
 * dashboard.js — Dashboard tab: KPI cards, charts, ticker view, trade log
 * NexusTrader Dashboard v2
 */

const Dashboard = {
  chart: null,
  weightsChart: null,
  chartSeries: {},
  chartType: 'candles', // 'candles' or 'line'
  chartData: [],        // cached loaded data

  init() {
    this.initCharts();
    // Listen for updates
    document.addEventListener('nt:initState', (e) => this.onInitState(e.detail));
    document.addEventListener('nt:wsMessage', (e) => this.onWSMessage(e.detail));
    document.addEventListener('nt:tickerChange', (e) => this.onTickerChange(e.detail));
    document.addEventListener('nt:statusUpdate', (e) => this.onStatusUpdate(e.detail));
    // Chart type toggle buttons
    document.querySelectorAll('.chart-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.chartType = btn.dataset.type;
        this.redrawChart();
      });
    });
  },

  /** Redraw chart with current type and cached data */
  redrawChart() {
    if (!this.chart || !this.chartSeries.candles || !this.chartData.length) return;
    this.chartSeries.candles.setData([]);
    this.chartSeries.volume.setData([]);
    if (this.chartType === 'line') {
      // Line mode: use close prices only
      const lineData = this.chartData.map(d => ({
        time: d.time,
        value: d.close,
      }));
      // Replace candlestick with line by setting flat candles
      const flatData = this.chartData.map(d => ({
        time: d.time,
        open: d.close, high: d.close, low: d.close, close: d.close,
      }));
      this.chartSeries.candles.setData(flatData);
      // Add line series overlay
      this.chartSeries.candles.applyOptions({
        upColor: '#3b82f6',
        downColor: '#3b82f6',
        borderUpColor: '#3b82f6',
        borderDownColor: '#3b82f6',
        wickUpColor: '#3b82f6',
        wickDownColor: '#3b82f6',
      });
    } else {
      // Candlestick mode
      this.chartSeries.candles.applyOptions({
        upColor: '#10b981',
        downColor: '#f43f5e',
        borderUpColor: '#10b981',
        borderDownColor: '#f43f5e',
        wickUpColor: '#10b981',
        wickDownColor: '#f43f5e',
      });
      this.chartSeries.candles.setData(this.chartData);
    }
  },

  /** Initialize Lightweight Charts */
  initCharts() {
    try {
    // Price chart
    const chartEl = byId('main-chart');
    if (chartEl && LightweightCharts) {
      // Ensure chart container has dimensions
      if (!chartEl.clientWidth || !chartEl.clientHeight) {
        chartEl.style.width = chartEl.style.width || '100%';
        chartEl.style.height = chartEl.style.height || '400px';
      }
      this.chart = LightweightCharts.createChart(chartEl, {
        width: chartEl.clientWidth,
        height: chartEl.clientHeight || 400,
        layout: {
          background: { type: 'solid', color: 'transparent' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: 'rgba(255,255,255,0.04)' },
          horzLines: { color: 'rgba(255,255,255,0.04)' },
        },
        crosshair: { mode: 0 },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
        timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true },
      });
      this.chartSeries.candles = this.chart.addCandlestickSeries({
        upColor: '#10b981',
        downColor: '#f43f5e',
        borderUpColor: '#10b981',
        borderDownColor: '#f43f5e',
        wickUpColor: '#10b981',
        wickDownColor: '#f43f5e',
      });
      // Volume
      this.chartSeries.volume = this.chart.addHistogramSeries({
        color: 'rgba(59,130,246,0.3)',
        priceFormat: { type: 'volume' },
        priceScaleId: '',
      });
      this.chart.priceScale('').applyOptions({ scaleMargins: { top: 0.7, bottom: 0 } });
    }

    // Weights chart
    const wEl = byId('weights-chart');
    if (wEl) {
      const ctx = wEl.getContext('2d');
      this.weightsChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 10 } } } },
        },
      });
    }
    } catch(e) { console.error('initCharts failed:', e); }
  },

  /** Handle init state */
  async onInitState(data) {
    this.updateKPIs(data);
    this.renderTrades(data.trades || []);
    if (App.state.activeTicker !== 'portfolio') {
      this.loadHistory(App.state.activeTicker);
    }
    // Fetch weights on init too
    this.fetchWeights();
  },

  /** Fetch strategy weights from API */
  async fetchWeights() {
    try {
      const wData = await API.weights();
      if (wData && wData.weights) this.renderWeights(wData.weights);
    } catch (e) { /* weights fetch is best-effort */ }
  },

  /** Handle WebSocket messages */
  onWSMessage(msg) {
    if (msg.type === 'tick') {
      this.onTick(msg);
    } else if (msg.type === 'init_state' || msg.type === 'state') {
      this.onInitState(msg.data || msg);
    }
  },

  /** Handle tick data */
  onTick(msg) {
    try {
    const data = msg.data || msg;
    if (!data) return;

    // Update price
    if (data.price) {
      const el = byId('ticker-price');
      if (el) el.textContent = '$' + data.price.toFixed(2);
      if (data.change_pct) {
        const cel = byId('ticker-change');
        if (cel) {
          cel.textContent = (data.change_pct >= 0 ? '+' : '') + data.change_pct.toFixed(2) + '%';
          cel.style.color = data.change_pct >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        }
      }
    }

    // Update ticker tab prices
    if (data.ticker && data.price) {
      const tabEl = byId('tab-price-' + data.ticker);
      if (tabEl) tabEl.textContent = '$' + data.price.toFixed(2);
    }

    // Update chart (best-effort)
    if (data.ohlc && this.chartSeries && this.chartSeries.candles) {
      try {
        this.chartSeries.candles.update({
          time: data.timestamp || Math.floor(Date.now() / 1000),
          open: data.ohlc.open || data.price,
          high: data.ohlc.high || data.price,
          low: data.ohlc.low || data.price,
          close: data.price,
        });
      } catch (e) { /* chart update is best-effort */ }
    }

    // Update KPIs
    this.updateKPIs(data);

    // Simulation progress
    if (data.sim_progress !== undefined) {
      const container = byId('sim-progress-container');
      const bar = byId('sim-progress-bar');
      const label = byId('sim-progress-label');
      if (container && data.sim_progress > 0 && data.sim_progress < 100) {
        container.style.display = 'flex';
        if (bar) bar.style.width = data.sim_progress + '%';
        if (label) label.textContent = Math.round(data.sim_progress) + '%';
      } else if (container) {
        container.style.display = 'none';
      }
    }

    // Position details
    if (data.position) {
      this.renderPosition(data.position);
    }
    } catch (e) { /* ticks must never crash the dashboard */ }
  },

  /** Update KPI cards */
  updateKPIs(data) {
    try {
    if (data.equity !== undefined) { const el = byId('val-equity'); if (el) el.textContent = '$' + Number(data.equity).toFixed(2); }
    if (data.balance !== undefined) { const el = byId('val-balance'); if (el) el.textContent = '$' + Number(data.balance).toFixed(2); }
    if (data.unrealized_pnl !== undefined) {
      const pnl = data.unrealized_pnl;
      const el = byId('val-unrealized-pnl');
      if (el) {
        el.textContent = 'Active Trade Profit: $' + pnl.toFixed(2);
        el.style.color = pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
      }
    }
    if (data.winrate !== undefined) { const el = byId('val-winrate'); if (el) el.textContent = (data.winrate * 100).toFixed(1) + '%'; }
    const tc = data.today_trade_count ?? data.trade_count ?? (typeof data.closed_trades === 'number' ? data.closed_trades : (Array.isArray(data.trades) ? data.trades.length : undefined));
    if (tc !== undefined) { const el = byId('val-trade-count'); if (el) el.textContent = tc + ' trades completed'; }
    if (data.total_pnl !== undefined) {
      const el = byId('val-total-pnl');
      if (el) el.textContent = '$' + data.total_pnl.toFixed(2);
      const el2 = byId('val-total-pnl-percent');
      if (el2 && data.total_pnl_pct !== undefined) {
        el2.textContent = (data.total_pnl_pct >= 0 ? '+' : '') + data.total_pnl_pct.toFixed(2) + '%';
        el2.style.color = data.total_pnl_pct >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
      }
    }
    const portEl = byId('tab-portfolio-equity');
    if (portEl && data.equity !== undefined) portEl.textContent = '$' + data.equity.toFixed(2);
    } catch(e) { /* KPIs are visual-only, never break the page */ }
  },

  /** Load chart history for ticker */
  async loadHistory(ticker) {
    if (ticker === 'portfolio' || !this.chart || !this.chartSeries.candles) return;
    try {
      const infoEl = byId('chart-data-info');
      if (infoEl) infoEl.textContent = 'Loading ' + ticker + '...';

      const data = await API.history(ticker);
      if (!data || (Array.isArray(data) && !data.length)) {
        if (infoEl) infoEl.textContent = 'No data for ' + ticker;
        return;
      }

      const rows = Array.isArray(data) ? data : (data.candles || data.data || []);
      if (!rows.length) {
        if (infoEl) infoEl.textContent = 'Empty dataset';
        return;
      }

      // Parse timestamp to Unix seconds
      const toTime = (ts) => {
        if (typeof ts === 'number') return ts < 1e12 ? ts : ts / 1000;
        if (typeof ts === 'string') {
          const d = new Date(ts);
          return isNaN(d.getTime()) ? null : Math.floor(d.getTime() / 1000);
        }
        return null;
      };

      const candleData = [];
      for (const c of rows) {
        const time = toTime(c.timestamp || c.time);
        if (time == null) continue;
        const open = Number(c.open ?? c.close ?? c.price ?? 0);
        const high = Number(c.high ?? c.close ?? c.price ?? 0);
        const low = Number(c.low ?? c.close ?? c.price ?? 0);
        const close = Number(c.close ?? c.price ?? 0);
        if (isNaN(open) || isNaN(close)) continue;
        candleData.push({ time, open, high, low, close });
      }

      if (!candleData.length) {
        if (infoEl) infoEl.textContent = 'No valid candles';
        return;
      }

      // Sort by time ascending (required by lightweight-charts)
      candleData.sort((a, b) => a.time - b.time);

      // Cache data for chart type switching
      this.chartData = candleData;
      if (infoEl) infoEl.textContent = candleData.length + ' candles loaded';

      // Render according to current chart type
      this.redrawChart();

      // Volume (the /api/history endpoint doesn't return volume, so skip)
      // Volume is optional — only attempt if data has volume field
      const hasVolume = rows.some(r => r.volume != null);
      if (hasVolume && this.chartSeries.volume) {
        const volData = [];
        for (const v of rows) {
          const time = toTime(v.timestamp || v.time);
          const vol = Number(v.volume || 0);
          if (time == null || isNaN(vol)) continue;
          volData.push({ time, value: vol, color: 'rgba(59,130,246,0.15)' });
        }
        if (volData.length) this.chartSeries.volume.setData(volData);
      }
    } catch (e) {
      console.error('Failed to load history:', e);
      const infoEl = byId('chart-data-info');
      if (infoEl) infoEl.textContent = 'Chart error: ' + e.message;
    }
  },

  /** Handle ticker change */
  onTickerChange(ticker) {
    if (ticker !== 'portfolio') this.loadHistory(ticker);
  },

  /** Handle status update */
  async onStatusUpdate(data) {
    this.updateKPIs(data);
    if (data.trades) this.renderTrades(data.trades);
    if (data.weights) this.renderWeights(data.weights);
    if (data.probability) this.renderProbability(data.probability);

    // Fetch weights separately since /api/status doesn't include them
    try {
      const wData = await API.weights();
      if (wData && wData.weights) this.renderWeights(wData.weights);
    } catch (e) { /* weights are optional */ }
  },

  /** Render trade log */
  renderTrades(trades) {
    const tbody = byId('recent-trades-list');
    if (!tbody) return;
    if (!trades || trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-secondary);text-align:center;padding:20px">No trades yet</td></tr>';
      return;
    }
    tbody.innerHTML = trades.slice(0, 20).map(t => `
      <tr>
        <td style="color:var(--text-secondary)">${(t.entry_time || t.exit_time || t.timestamp || t.time) ? new Date((t.entry_time || t.exit_time || t.timestamp || t.time) * 1000).toLocaleDateString() : ''}</td>
        <td>${t.symbol || t.ticker || ''}</td>
        <td style="color:${t.direction === 'long' ? 'var(--neon-green)' : 'var(--neon-red)'}">${t.direction || ''}</td>
        <td>$${(t.entry_price || 0).toFixed(2)}</td>
        <td>$${(t.exit_price || 0).toFixed(2)}</td>
        <td style="color:${(t.pnl || 0) >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'}">${t.pnl_pct !== undefined ? (t.pnl_pct >= 0 ? '+' : '') + t.pnl_pct.toFixed(2) + '%' : '$' + (t.pnl || 0).toFixed(2)}</td>
      </tr>
    `).join('');
  },

  /** Render strategy weights */
  renderWeights(weights) {
    const container = byId('weights-container');
    if (!container) return;
    if (!weights || Object.keys(weights).length === 0) {
      container.innerHTML = '<span style="color:var(--text-secondary)">No weights loaded</span>';
      return;
    }
    container.innerHTML = Object.entries(weights).map(([name, w]) => `
      <div class="weight-bar">
        <span class="weight-label">${name}</span>
        <div class="weight-fill" style="width:${(w * 100).toFixed(0)}%"></div>
        <span class="weight-val">${(w * 100).toFixed(1)}%</span>
      </div>
    `).join('');

    // Update doughnut
    if (this.weightsChart) {
      this.weightsChart.data.labels = Object.keys(weights);
      this.weightsChart.data.datasets[0].data = Object.values(weights);
      this.weightsChart.data.datasets[0].backgroundColor = [
        '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4',
      ];
      this.weightsChart.update();
    }
  },

  /** Render position details */
  renderPosition(position) {
    const container = byId('position-details-container');
    if (!container) return;
    if (!position || !position.entry_price) {
      container.innerHTML = '<span style="color:var(--text-secondary)">No active position</span>';
      return;
    }
    const dir = position.direction || 'long';
    const color = dir === 'long' ? 'var(--neon-green)' : 'var(--neon-red)';
    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <span style="color:${color};font-weight:600">${dir.toUpperCase()}</span>
        <span>Entry: <b>$${(position.entry_price || 0).toFixed(2)}</b></span>
        <span>Size: <b>${(position.size || 0).toFixed(4)}</b></span>
        <span>PnL: <b style="color:${(position.unrealized_pnl || 0) >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'}">$${(position.unrealized_pnl || 0).toFixed(2)}</b></span>
      </div>
    `;
  },

  /** Render probability panel */
  renderProbability(prob) {
    if (!prob) return;
    if (prob.probability !== undefined) {
      byId('prob-value').textContent = `${(prob.probability * 100).toFixed(1)}%`;
      byId('prob-gauge').style.width = `${(prob.probability * 100).toFixed(0)}%`;
    }
    if (prob.ev !== undefined) byId('val-ev').textContent = `$${prob.ev.toFixed(2)}`;
    if (prob.risk_reward !== undefined) byId('val-rr').textContent = prob.risk_reward.toFixed(2);
    if (prob.kelly_fraction !== undefined) byId('val-kelly').textContent = `${(prob.kelly_fraction * 100).toFixed(1)}%`;
    if (prob.signal_strength !== undefined) byId('val-sig-strength').textContent = `${(prob.signal_strength * 100).toFixed(1)}%`;
    if (prob.viable !== undefined) {
      const badge = byId('viability-badge');
      badge.textContent = prob.viable ? 'VIABLE' : 'NO TRADE';
      badge.style.background = prob.viable ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)';
      badge.style.color = prob.viable ? 'var(--neon-green)' : 'var(--neon-red)';
    }
  },
};

// Init when ready
document.addEventListener('DOMContentLoaded', () => {
  Dashboard.init();
  // Ensure icons render after charts init
  if (typeof lucide !== 'undefined') {
    setTimeout(() => lucide.createIcons(), 100);
  }
});
