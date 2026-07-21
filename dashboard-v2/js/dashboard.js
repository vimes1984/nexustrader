/**
 * dashboard.js v3 — Main dashboard tab: charts, KPIs, trade log, weights
 */
const Dashboard = {
  chart: null, weightsChart: null, chartSeries: {}, chartType: 'candles', chartData: [],

  init() {
    try { this.initCharts(); } catch(e) { console.error('Chart init failed:', e); }
    document.addEventListener('nt:initState', (e) => this.onInitState(e.detail));
    document.addEventListener('nt:wsMessage', (e) => this.onWSMessage(e.detail));
    document.addEventListener('nt:tickerChange', (e) => this.onTickerChange(e.detail));
    document.addEventListener('nt:statusUpdate', (e) => this.onStatusUpdate(e.detail));

    document.querySelectorAll('.chart-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.chartType = btn.dataset.type;
        this.redrawChart();
      });
    });
    lucide?.createIcons();
  },

  initCharts() {
    const chartEl = byId('main-chart');
    if (!chartEl || typeof LightweightCharts === 'undefined') return;

    this.chart = LightweightCharts.createChart(chartEl, {
      width: chartEl.clientWidth || 800,
      height: chartEl.clientHeight || 420,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true },
    });

    this.chartSeries.candles = this.chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#f43f5e',
      borderUpColor: '#10b981', borderDownColor: '#f43f5e',
      wickUpColor: '#10b981', wickDownColor: '#f43f5e',
    });
    this.chartSeries.volume = this.chart.addHistogramSeries({
      color: 'rgba(59,130,246,0.25)', priceFormat: { type: 'volume' }, priceScaleId: '',
    });
    this.chart.priceScale('').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });

    // Doughnut chart for weights
    const wEl = byId('weights-chart');
    if (wEl && typeof Chart !== 'undefined') {
      const ctx = wEl.getContext('2d');
      this.weightsChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: [], datasets: [{ data: [], backgroundColor: ['#3b82f6','#10b981','#f59e0b','#8b5cf6','#ec4899','#06b6d4','#f43f5e','#84cc16'] }] },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: '65%',
          plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 10 }, padding: 12 } } },
        },
      });
    }

    // Resize handler
    this._resizeHandler = () => {
      if (this.chart && chartEl.clientWidth) {
        this.chart.applyOptions({ width: chartEl.clientWidth, height: chartEl.clientHeight || 420 });
      }
    };
    window.addEventListener('resize', this._resizeHandler);
  },

  redrawChart() {
    if (!this.chart?.chartSeries?.candles || !this.chartData?.length) return;
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
    this.renderTrades(data.trades || []);
    if (App.state.activeTicker !== 'portfolio') this.loadHistory(App.state.activeTicker);
    this.fetchWeights();
  },

  async fetchWeights() {
    try {
      const d = await API.weights();
      if (d?.weights) this.renderWeights(d.weights);
    } catch(e) {}
  },

  onWSMessage(msg) {
    if (msg.type === 'tick') this.onTick(msg);
    else if (msg.type === 'init_state' || msg.type === 'state') this.onInitState(msg.data || msg);
  },

  onTick(msg) {
    try {
      const data = msg.data || msg; if (!data) return;
      if (data.price != null) {
        byId('ticker-price').textContent = '$' + Number(data.price).toFixed(2);
        if (data.change_pct != null) {
          const cel = byId('ticker-change');
          cel.textContent = (data.change_pct >= 0 ? '+' : '') + Number(data.change_pct).toFixed(2) + '%';
          cel.style.color = data.change_pct >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        }
      }
      if (data.ticker && data.price != null) {
        const te = byId('tab-price-' + data.ticker);
        if (te) te.textContent = '$' + Number(data.price).toFixed(2);
      }
      if (data.price != null && this.chartSeries?.candles) {
        try { this.chartSeries.candles.update({ time: data.timestamp || Math.floor(Date.now()/1000), open: data.price, high: data.price, low: data.price, close: data.price }); } catch(e) {}
      }
      this.updateKPIs(data);
      if (data.sim_progress != null) {
        const c = byId('sim-progress-container'); const b = byId('sim-progress-bar'); const l = byId('sim-progress-label');
        if (data.sim_progress > 0 && data.sim_progress < 100) {
          if (c) c.style.display = 'flex';
          if (b) b.style.width = data.sim_progress + '%';
          if (l) l.textContent = Math.round(data.sim_progress) + '%';
        } else if (c) { c.style.display = 'none'; }
      }
      if (data.position) this.renderPosition(data.position);
    } catch(e) {}
  },

  updateKPIs(data) {
    try {
      if (data.equity != null) { const e = byId('val-equity'); if (e) e.textContent = '$' + Number(data.equity).toFixed(2); }
      if (data.balance != null) { const e = byId('val-balance'); if (e) e.textContent = '$' + Number(data.balance).toFixed(2); }
      if (data.unrealized_pnl != null) {
        const p = Number(data.unrealized_pnl); const e = byId('val-unrealized-pnl');
        if (e) { e.textContent = 'Active Trade PnL: $' + p.toFixed(2); e.style.color = p >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'; }
      }
      if (data.winrate != null) { const e = byId('val-winrate'); if (e) e.textContent = (Number(data.winrate)*100).toFixed(1) + '%'; }
      const tc = data.today_trade_count ?? data.trade_count ?? (typeof data.closed_trades === 'number' ? data.closed_trades : Array.isArray(data.trades) ? data.trades.length : undefined);
      if (tc != null) { const e = byId('val-trade-count'); if (e) e.textContent = tc + ' trades completed'; }
      if (data.total_pnl != null) {
        const p = Number(data.total_pnl); const e = byId('val-total-pnl'); if (e) { e.textContent = '$' + p.toFixed(2); e.style.color = p >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'; }
        const pct = data.total_pnl_pct; const e2 = byId('val-total-pnl-percent');
        if (e2 && pct != null) { e2.textContent = (pct>=0?'+':'') + Number(pct).toFixed(2)+'%'; e2.style.color = pct>=0?'var(--neon-green)':'var(--neon-red)'; }
      }
      const pe = byId('tab-portfolio-equity'); if (pe && data.equity != null) pe.textContent = '$' + Number(data.equity).toFixed(2);
    } catch(e) {}
  },

  async loadHistory(ticker) {
    if (ticker === 'portfolio' || !this.chartSeries?.candles) return;
    try {
      const infoEl = byId('chart-data-info'); if (infoEl) infoEl.textContent = '⏳ Loading ' + ticker + '...';
      const data = await API.history(ticker);
      const rows = Array.isArray(data) ? data : (data?.candles || data?.data || []);
      if (!rows?.length) { if (infoEl) infoEl.textContent = '⚠️ No data for ' + ticker; return; }

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
      if (!cd.length) { if (infoEl) infoEl.textContent = '⚠️ No valid candles'; return; }
      cd.sort((a,b) => a.time - b.time);

      this.chartData = cd;
      if (infoEl) infoEl.textContent = '📊 ' + cd.length + ' candles loaded';
      this.redrawChart();
    } catch(e) {
      console.error('History load failed:', e);
      byId('chart-data-info').textContent = '❌ Chart error';
    }
  },

  onTickerChange(ticker) { if (ticker !== 'portfolio') this.loadHistory(ticker); },

  async onStatusUpdate(data) {
    this.updateKPIs(data);
    if (data.trades) this.renderTrades(data.trades);
    if (data.weights) this.renderWeights(data.weights);
    if (data.probability) this.renderProbability(data.probability);
    this.fetchWeights();
  },

  renderTrades(trades) {
    const tbody = byId('recent-trades-list'); if (!tbody) return;
    if (!trades?.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:20px">No trades yet — bot is collecting data</td></tr>';
      return;
    }
    tbody.innerHTML = trades.slice(0, 20).map(t => {
      const entryTime = t.entry_time || t.exit_time || t.timestamp || t.time;
      const date = entryTime ? new Date(Number(entryTime) * 1000).toLocaleDateString() : '—';
      const dir = t.direction || '—';
      const dirColor = dir === 'long' ? 'var(--neon-green)' : dir === 'short' ? 'var(--neon-red)' : 'var(--text-secondary)';
      const pnl = Number(t.pnl || 0);
      const pnlStr = t.pnl_pct != null ? (pnl>=0?'+':'')+Number(t.pnl_pct).toFixed(2)+'%' : '$'+pnl.toFixed(2);
      return `<tr>
        <td style="color:var(--text-muted);font-size:10px">${date}</td>
        <td style="font-weight:600">${t.symbol || t.ticker || '—'}</td>
        <td style="color:${dirColor};font-weight:600">${dir.toUpperCase()}</td>
        <td style="font-family:var(--font-mono)">$${Number(t.entry_price||0).toFixed(2)}</td>
        <td style="font-family:var(--font-mono)">$${Number(t.exit_price||0).toFixed(2)}</td>
        <td style="color:${pnl>=0?'var(--neon-green)':'var(--neon-red)'};font-weight:600;font-family:var(--font-mono)">${pnlStr}</td>
      </tr>`;
    }).join('');
  },

  renderWeights(weights) {
    const c = byId('weights-container'); if (!c) return;
    if (!weights || !Object.keys(weights).length) {
      c.innerHTML = '<span style="color:var(--text-muted);font-size:11px">No weights available</span>';
    } else {
      const maxW = Math.max(...Object.values(weights), 0.01);
      c.innerHTML = Object.entries(weights).map(([n,w]) => `
        <div class="weight-bar">
          <span class="weight-label">${n}</span>
          <div class="weight-fill" style="width:${(w/maxW*100).toFixed(0)}%;opacity:${0.4+(w/maxW*0.6).toFixed(1)}"></div>
          <span class="weight-val">${(w*100).toFixed(1)}%</span>
        </div>`).join('');
    }
    if (this.weightsChart) {
      this.weightsChart.data.labels = Object.keys(weights||{});
      this.weightsChart.data.datasets[0].data = Object.values(weights||{});
      this.weightsChart.update();
    }
  },

  renderPosition(pos) {
    const c = byId('position-details-container'); if (!c) return;
    if (!pos?.entry_price) { c.innerHTML = '<span style="color:var(--text-muted)">No active position</span>'; return; }
    const dir = pos.direction || 'long';
    const dirColor = dir === 'long' ? 'var(--neon-green)' : 'var(--neon-red)';
    const pnl = Number(pos.unrealized_pnl || 0);
    c.innerHTML = `<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">
      <span style="color:${dirColor};font-weight:700;font-size:13px">${dir.toUpperCase()}</span>
      <span style="font-family:var(--font-mono)">Entry: <b>$${Number(pos.entry_price).toFixed(2)}</b></span>
      <span style="font-family:var(--font-mono)">Size: <b>${Number(pos.size||0).toFixed(4)}</b></span>
      <span style="font-family:var(--font-mono)">PnL: <b style="color:${pnl>=0?'var(--neon-green)':'var(--neon-red)'}">$${pnl.toFixed(4)}</b></span>
    </div>`;
  },

  renderProbability(prob) {
    if (!prob) return;
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

document.addEventListener('DOMContentLoaded', () => { Dashboard.init(); lucide?.createIcons(); });
