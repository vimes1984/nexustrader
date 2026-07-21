/**
 * architecture.js v3 — System architecture diagram tab
 */
const Architecture = {
  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'architecture') this.load(); });
    byId('btn-refresh-arch')?.addEventListener('click', () => this.load());
  },

  load() {
    const el = byId('architecture-diagram'); if (!el) return;

    // Dynamic: fetch architecture data from API, fallback to static diagram
    API.architecture().then(data => {
      this.render(data);
    }).catch(() => {
      this.render(null);
    });
  },

  render(data) {
    const el = byId('architecture-diagram'); if (!el) return;

    const services = data?.services || data?.layers || [];
    const metrics = data?.metrics || {};

    const layers = [
      { name: 'Dashboard UI', color: 'var(--neon-blue)', icon: '🖥️', desc: 'Modular SPA — 11 JS modules, real-time WS updates, LightweightCharts + Chart.js', components: ['index.html', 'api.js', 'router.js', 'dashboard.js', '*.js'] },
      { name: 'API Gateway', color: 'var(--neon-green)', icon: '🔌', desc: 'FastAPI REST — 53+ endpoints, WebSocket streaming, CORS, error middleware', components: ['main.py', '/api/status', '/api/weights', '/api/neural/*'] },
      { name: 'Trading Engine', color: 'var(--neon-purple)', icon: '⚙️', desc: 'Orchestrator → SimulatedTrader — RL policy decisions, ensemble voting, Kelly sizing', components: ['orchestrator.py', 'sim_trader.py', 'learning_engine.py', 'mutation_guard.py'] },
      { name: 'Strategy Layer', color: 'var(--neon-yellow)', icon: '📊', desc: 'Multi-strategy ensemble: trend, momentum, mean-reversion, volatility, ML signals', components: ['strategies/*.py', 'ensemble.py', 'probability_engine.py'] },
      { name: 'Data Layer', color: 'var(--neon-cyan)', icon: '💾', desc: 'SQLite + OHLCV fetcher — real-time price feeds, historical data, trade logging', components: ['db_manager.py', 'data_fetcher.py', 'historical_pipeline.py'] },
      { name: 'Broker / Exchange', color: 'var(--neon-red)', icon: '🏦', desc: 'Kraken / Coinbase / Binance — paper & live modes, order execution, balance tracking', components: ['execution_engine.py', 'trading_modes.py', 'performance_metrics.py'] },
      { name: 'AI / LLM Layer', color: 'var(--neon-pink)', icon: '🧠', desc: 'Llama 3.2 3B fine-tuned, RAG pipeline, sentiment, regime detection, prompt management', components: ['llama-server', 'rag_pipeline.py', 'openclaw_bridge.py', 'proton_bridge.py'] },
    ];

    let html = '<div style="display:flex;flex-direction:column;gap:10px;margin-top:12px">';

    layers.forEach((l, i) => {
      const borderSide = i % 2 === 0 ? 'border-left' : 'border-right';
      const metricKeys = { 'Trading Engine': ['uptime_seconds', 'trades_completed'], 'Data Layer': ['candles_loaded'], 'API Gateway': ['endpoint_count'] };
      const km = metricKeys[l.name] || [];
      const extras = km.filter(k => metrics?.[k] != null).map(k => `<span style="font-size:9px;color:var(--text-muted)">${k}: ${metrics[k]}</span>`).join(' · ');

      html += `<div class="glass-panel" style="padding:14px 16px;${borderSide}:3px solid ${l.color};margin-bottom:4px;position:relative">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
          <div>
            <div style="font-weight:700;font-size:14px;color:${l.color};margin-bottom:4px">${l.icon} ${l.name}</div>
            <div style="font-size:11px;color:var(--text-secondary);line-height:1.5">${l.desc}</div>
            <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px">${l.components.map(c => `<code style="font-size:9px;font-family:var(--font-mono);background:rgba(255,255,255,0.04);padding:2px 6px;border-radius:3px;color:var(--text-muted)">${c}</code>`).join('')}</div>
          </div>
          <div style="text-align:right;min-width:120px">
            <span style="font-size:32px;opacity:0.3">${String(i+1).padStart(2,'0')}</span>
            ${extras ? `<div style="font-size:9px;color:var(--text-muted);margin-top:4px">${extras}</div>` : ''}
          </div>
        </div>
        ${i < layers.length - 1 ? `<div style="text-align:center;padding:4px 0;color:${layers[i+1].color};font-size:14px;opacity:0.4">║<br>⬇</div>` : ''}
      </div>`;
    });

    // Service map
    if (services.length) {
      html += `<div class="glass-panel" style="padding:14px 16px;margin-top:8px">
        <div class="section-title">Service Map</div>
        <table class="trade-table" style="margin-top:8px">
          <thead><tr><th>Service</th><th>Host</th><th>Port</th><th>Status</th></tr></thead>
          <tbody>${services.map(s => `<tr>
            <td style="font-weight:600">${s.name}</td>
            <td style="font-family:var(--font-mono);font-size:10px">${s.host || '—'}</td>
            <td style="font-family:var(--font-mono);font-size:10px">${s.port || '—'}</td>
            <td><span style="color:${s.status==='up'?'var(--neon-green)':'var(--neon-red)'};font-size:10px">${s.status==='up'?'● Up':'○ Down'}</span></td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
    }

    html += '</div>';
    el.innerHTML = html;
    lucide?.createIcons();
  },
};

document.addEventListener('DOMContentLoaded', () => { Architecture.init(); lucide?.createIcons(); });
