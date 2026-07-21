/**
 * dashboard.js — Dashboard tab: KPI cards, charts, ticker view, trade log
 * NexusTrader Dashboard v2
 */

const Dashboard = {
  chart: null,
  weightsChart: null,
  chartSeries: {},

  init() {
    this.initCharts();
    // Listen for updates
    document.addEventListener('nt:initState', (e) => this.onInitState(e.detail));
    document.addEventListener('nt:wsMessage', (e) => this.onWSMessage(e.detail));
    document.addEventListener('nt:tickerChange', (e) => this.onTickerChange(e.detail));
    document.addEventListener('nt:statusUpdate', (e) => this.onStatusUpdate(e.detail));
  },

  /** Initialize Lightweight Charts */
  initCharts() {
    // Price chart
    const chartEl = byId('main-chart');
    if (chartEl) {
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
  },

  /** Handle init state */
  async onInitState(data) {
    this.updateKPIs(data);
    this.renderTrades(data.trades || []);
    if (App.state.activeTicker !== 'portfolio') {
      this.loadHistory(App.state.activeTicker);
    }
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

    // Update chart
    if (data.ohlc && this.chartSeries.candles) {
      this.chartSeries.candles.update({
        time: data.timestamp || Math.floor(Date.now() / 1000),
        open: data.ohlc.open || data.price,
        high: data.ohlc.high || data.price,
        low: data.ohlc.low || data.price,
        close: data.price,
      });
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
    } catch(e) { /* ticks must never crash the dashboard */ }
  },

  /** Update KPI cards */
  updateKPIs(data) {
    try {
    if (data.equity !== undefined) { const el = byId('val-equity'); if (el) el.textContent = '$' + data.equity.toFixed(2); }
    if (data.balance !== undefined) { const el = byId('val-balance'); if (el) el.textContent = '$' + data.balance.toFixed(2); }
    if (data.unrealized_pnl !== undefined) {
      const pnl = data.unrealized_pnl;
      const el = byId('val-unrealized-pnl');
      if (el) {
        el.textContent = 'Active Trade Profit: $' + pnl.toFixed(2);
        el.style.color = pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
      }
    }
    if (data.winrate !== undefined) { const el = byId('val-winrate'); if (el) el.textContent = (data.winrate * 100).toFixed(1) + '%'; }
    if (data.trade_count !== undefined) { const el = byId('val-trade-count'); if (el) el.textContent = data.trade_count + ' trades completed'; }
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
    if (ticker === 'portfolio') return;
    try {
      const data = await API.history(ticker);
      if (data.candles && this.chartSeries.candles) {
        const candleData = data.candles.map(c => ({
          time: c.timestamp || c.time,
          open: c.open, high: c.high, low: c.low, close: c.close,
        }));
        this.chartSeries.candles.setData(candleData);
      }
      if (data.volumes && this.chartSeries.volume) {
        const volData = data.volumes.map(v => ({
          time: v.timestamp || v.time,
          value: v.volume,
          color: v.close >= v.open ? 'rgba(16,185,129,0.2)' : 'rgba(244,63,94,0.2)',
        }));
        this.chartSeries.volume.setData(volData);
      }
    } catch (e) {
      console.error('Failed to load history:', e);
    }
  },

  /** Handle ticker change */
  onTickerChange(ticker) {
    if (ticker !== 'portfolio') this.loadHistory(ticker);
  },

  /** Handle status update */
  onStatusUpdate(data) {
    this.updateKPIs(data);
    if (data.trades) this.renderTrades(data.trades);
    if (data.weights) this.renderWeights(data.weights);
    if (data.probability) this.renderProbability(data.probability);
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
        <td style="color:var(--text-secondary)">${t.timestamp || t.time || ''}</td>
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
document.addEventListener('DOMContentLoaded', () => Dashboard.init());
