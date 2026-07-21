/**
 * logs.js — System Logs tab + Architecture diagram + Strategy/LongTerm tabs
 */
const Logs = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'logs') this.refresh();
      if (e.detail === 'architecture') this.loadArchitecture();
      if (e.detail === 'strategy') this.loadStrategy();
    });
    byId('btn-refresh-logs')?.addEventListener('click', () => this.refresh());
    byId('btn-refresh-arch')?.addEventListener('click', () => this.loadArchitecture());
    byId('btn-refresh-strategy')?.addEventListener('click', () => this.loadStrategy());
  },

  async refresh() {
    try {
      const data = await API.systemLogs(300);
      const el = byId('system-logs');
      if (!el) return;
      if (data.logs && data.logs.length > 0) {
        el.innerHTML = data.logs.slice(-200).map(l => `
          <div style="font-family:monospace;font-size:11px;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.02)">
            <span style="color:var(--text-secondary)">${l.timestamp || ''}</span>
            <span style="color:${this.logColor(l.level)};margin:0 6px">[${l.level || 'INFO'}]</span>
            <span>${l.message || l.text || ''}</span>
          </div>
        `).join('');
      } else {
        el.innerHTML = '<p style="color:var(--text-secondary)">No logs available</p>';
      }
    } catch (e) {
      App.toast('Failed to load logs', 'error');
    }
  },

  logColor(level) {
    const map = { ERROR: 'var(--neon-red)', WARNING: 'var(--neon-yellow)', WARN: 'var(--neon-yellow)', INFO: 'var(--text-secondary)', DEBUG: '#64748b' };
    return map[level] || 'var(--text-secondary)';
  },

  async loadArchitecture() {
    try {
      const data = await API.status();
      const el = byId('architecture-diagram');
      if (!el) return;
      // Render a simple text-based architecture view
      el.innerHTML = `
        <div class="glass-panel" style="padding:16px;margin-bottom:8px">
          <h3 style="color:var(--neon-blue);margin-bottom:8px">System Architecture</h3>
          <pre style="font-size:11px;line-height:1.6;color:var(--text-secondary)">
┌─────────────────────────────────────────────────┐
│                 ${data.trading_mode || 'LIVE'} MODE                        │
│  Tickers: ${(data.tickers || []).join(', ') || 'None'}              │
│  Balance: $${(data.balance || 0).toFixed(2)}                        │
│  Equity:  $${(data.equity || 0).toFixed(2)}                         │
├─────────────────────────────────────────────────┤
│  📡 Data Ingestion → ${(data.tickers || []).length} tickers via WebSocket    │
│  🧠 Strategy Ensemble → 6 strategies per ticker     │
│  ⚖️  Probability Engine → Kelly + EV + RR            │
│  📊 Policy Network → RL weight optimization         │
│  💰 Execution Engine → ${data.trading_mode === 'live' ? 'Live Kraken' : 'Simulated'}          │
├─────────────────────────────────────────────────┤
│  🤖 Quant Team: 9 agents (cron + manual)           │
│  🔮 LLaMA: ${data.llm_connected ? 'Connected' : 'Disconnected'}                          │
│  📈 Chart: Lightweight Charts + Chart.js            │
└─────────────────────────────────────────────────┘</pre>
        </div>`;
    } catch (e) { /* silent */ }
  },

  async loadStrategy() {
    try {
      const data = await API.signals();
      const el = byId('strategy-panel');
      if (!el) return;
      el.innerHTML = data.signals
        ? `<pre style="font-size:12px;white-space:pre-wrap;color:var(--text-secondary)">${JSON.stringify(data, null, 2)}</pre>`
        : '<p style="color:var(--text-secondary)">No active signals</p>';
    } catch (e) { /* silent */ }
  },
};
document.addEventListener('DOMContentLoaded', () => Logs.init());
