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
      const el = byId('system-logs');
      if (!el) return;
      el.innerHTML = '<p style="color:var(--text-secondary)">Loading logs...</p>';
      const data = await API.systemLogs(300);
      if (!data || !data.logs) {
        el.innerHTML = '<p style="color:var(--text-secondary)">No log data available</p>';
        return;
      }
      // API returns logs as either: string (raw text), array of objects, or array of strings
      if (typeof data.logs === 'string') {
        // Raw text — split by newlines, try to parse timestamps
        const lines = data.logs.split('\n').filter(l => l.trim());
        if (!lines.length) {
          el.innerHTML = '<p style="color:var(--text-secondary)">' + data.logs + '</p>';
          return;
        }
        el.innerHTML = lines.slice(-200).map(line => {
          // Try to colorize by level keywords
          let color = 'var(--text-secondary)';
          const upper = line.toUpperCase();
          if (upper.includes('ERROR') || upper.includes('CRITICAL') || upper.includes('FATAL')) color = 'var(--neon-red)';
          else if (upper.includes('WARN')) color = 'var(--neon-yellow)';
          else if (upper.includes('DEBUG')) color = '#64748b';
          return '<div style="font-family:monospace;font-size:11px;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.02);color:' + color + '">' +
            line.replace(/</g, '&lt;') +
          '</div>';
        }).join('');
      } else if (Array.isArray(data.logs) && data.logs.length) {
        // Array of objects
        el.innerHTML = data.logs.slice(-200).map(l => {
          if (typeof l === 'string') return '<div style="font-family:monospace;font-size:11px;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.02)">' + l.replace(/</g, '&lt;') + '</div>';
          const ts = l.timestamp || l.time || '';
          const level = (l.level || 'INFO').toUpperCase();
          const msg = l.message || l.text || l.msg || '';
          return '<div style="font-family:monospace;font-size:11px;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.02)">' +
            '<span style="color:var(--text-secondary)">' + ts + '</span> ' +
            '<span style="color:' + this.logColor(level) + ';margin:0 6px">[' + level + ']</span> ' +
            '<span>' + msg.replace(/</g, '&lt;') + '</span>' +
          '</div>';
        }).join('');
      } else {
        el.innerHTML = '<p style="color:var(--text-secondary)">No log entries recorded yet</p>';
      }
    } catch (e) {
      const el = byId('system-logs');
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">Failed to load logs: ' + e.message + '</p>';
    }
  },

  logColor(level) {
    const map = { ERROR: 'var(--neon-red)', WARNING: 'var(--neon-yellow)', WARN: 'var(--neon-yellow)', INFO: 'var(--text-secondary)', DEBUG: '#64748b' };
    return map[level] || 'var(--text-secondary)';
  },

  async loadArchitecture() {
    try {
      const el = byId('architecture-diagram');
      if (!el) return;
      el.innerHTML = '<p style="color:var(--text-secondary)">Loading architecture...</p>';
      const data = await API.status();
      if (!data) throw new Error('No data');
      
      const tickers = (data.tickers || []).join(', ') || 'none';
      const time = new Date().toISOString().replace('T', ' ').slice(0, 19);
      
      el.innerHTML = 
        '<div class="glass-panel" style="padding:20px;margin-bottom:10px">' +
          '<h3 style="color:var(--neon-blue);margin:0 0 12px 0">🚀 NexusTrader System Architecture</h3>' +
          '<pre style="font-size:11px;line-height:1.6;color:var(--text-secondary);margin:0;background:rgba(0,0,0,0.2);padding:16px;border-radius:8px">' +
'┌────────────────────────────────────────────────────────────────┐\n' +
'│                    NEXUSTRADER v1.1                            │\n' +
'│              Mode: ' + (data.trading_mode || 'paper').toUpperCase().padEnd(41) + '│\n' +
'│              Uptime: ' + String(Math.floor((data.uptime_seconds||0)/60)).padEnd(39) + '│\n' +
'│              Updated: ' + time.padEnd(38) + '│\n' +
'├────────────────────────────────────────────────────────────────┤\n' +
'│                                                                │\n' +
'│  📡 DATA INGESTION LAYER                                       │\n' +
'│     Kraken WebSocket → ' + (data.tickers||[]).length + ' ticker(s) → Real-time OHLCV           │\n' +
'│                                                                │\n' +
'│  🔬 FEATURE ENGINE                                             │\n' +
'│     RSI · MACD · BBands · ATR · OBV · VWAP · Stochastic       │\n' +
'│     EMA Cross · Volume Profile · PPO · ADX · CCI              │\n' +
'│                                                                │\n' +
'│  🧠 STRATEGY ENSEMBLE (6 strategies per ticker)               │\n' +
'│     MeanReversion · Momentum · TrendFollowing · Breakout      │\n' +
'│     MLSignal · PatternRecognition                              │\n' +
'│                                                                │\n' +
'│  ⚖️  PROBABILITY ENGINE                                        │\n' +
'│     Kelly Criterion · Expected Value · Risk/Reward            │\n' +
'│     Signal Weighting · Regime Detection · Volatility Scaling  │\n' +
'│                                                                │\n' +
'│  🧬 POLICY NETWORK (Reinforcement Learning)                   │\n' +
'│     NN-ARCH-C93B8F — 6 actions · Adaptive LR                  │\n' +
'│     Experience Replay · Policy Gradient · TD Learning         │\n' +
'│                                                                │\n' +
'│  💰 EXECUTION ENGINE                                           │\n' +
'│     ' + (data.trading_mode === 'live' ? 'LIVE KRAKEN EXECUTION'.padEnd(57) : 'Paper Trading (Simulation)'.padEnd(57)) + '│\n' +
'│     Position Sizing · SL/TP · Trailing Stop · Cooldown Mgmt  │\n' +
'│                                                                │\n' +
'│  🛡️  RISK MANAGEMENT                                           │\n' +
'│     KillSwitch · Max Drawdown · Correlation Hedge             │\n' +
'│     Position Limits · Daily Goal Tracking · Circuit Breakers  │\n' +
'│                                                                │\n' +
'│  🤖 QUANT TEAM (AI Agents)                                    │\n' +
'│     Quant Optimizer · Risk Auditor · Allocator · Asset Sel.   │\n' +
'│     Developer · Strategist · Reviewer · Archival · Sentinel  │\n' +
'│                                                                │\n' +
'│  🔮 LLM INTEGRATION                                            │\n' +
'│     ' + (data.llm_connected ? 'Llama 3.2 3B (chris-System:8080)'.padEnd(57) : 'DISCONNECTED'.padEnd(57)) + '│\n' +
'│     Sentiment Analysis · Market Regime · Strategy Reasoning  │\n' +
'│                                                                │\n' +
'│  📊 DASHBOARD                                                  │\n' +
'│     Lightweight Charts + Chart.js · Real-time WebSocket       │\n' +
'│     Self-hosted (no CDN) · Nginx TLS 1.3 · FastAPI backend   │\n' +
'│                                                                │\n' +
'├────────────────────────────────────────────────────────────────┤\n' +
'│                                                                │\n' +
'│  📈 KEY METRICS                                                │\n' +
'│     Balance: $' + ((data.balance||0)).toFixed(2).padEnd(47) + '│\n' +
'│     Equity:  $' + ((data.equity||0)).toFixed(2).padEnd(47) + '│\n' +
'│     Closed Trades: ' + String(data.closed_trades||0).padEnd(41) + '│\n' +
'│     Win/Loss: ' + (data.win_count||0) + '/' + (data.loss_count||0).toString().padEnd(46) + '│\n' +
'│     Max Drawdown: ' + String(data.max_drawdown_pct||0) + ' %'.padEnd(42) + '│\n' +
'│     Health: ' + (data.health_status||'unknown').padEnd(49) + '│\n' +
'│                                                                │\n' +
'└────────────────────────────────────────────────────────────────┘</pre>' +
        '</div>' +
        '<div class="glass-panel" style="padding:16px;margin-bottom:8px">' +
          '<h3 style="color:var(--neon-green);margin:0 0 8px 0">🔗 Service Map</h3>' +
          '<pre style="font-size:11px;color:var(--text-secondary);margin:0">' +
'nexustrader.local:443 (nginx)\n' +
'  ├── /api/*         → FastAPI :8000 (NexusTrader bot)\n' +
'  ├── /dashboard-v2/ → Static SPA (9 JS modules)\n' +
'  └── WebSocket       → ws:// :8000/ws\n' +
'\n' +
'External Services:\n' +
'  ├── 192.168.0.77:8080 → llama-server (Llama 3.2 3B)\n' +
'  ├── 192.168.0.77:10250 → Proton Mail Bridge (socat)\n' +
'  └── Kraken WebSocket → Real-time market data\n' +
'</pre>' +
        '</div>';
    } catch (e) {
      const el = byId('architecture-diagram');
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">Failed to load architecture: ' + e.message + '</p>';
    }
  },

  async loadStrategy() {
    try {
      const el = byId('strategy-panel');
      if (!el) return;
      el.innerHTML = '<p style="color:var(--text-secondary)">Loading strategy data...</p>';
      const data = await API.signals();
      if (!data || (Array.isArray(data) && !data.length) || (typeof data === 'object' && !Object.keys(data).length)) {
        el.innerHTML = '<p style="color:var(--text-secondary)">No active signals — bot is idle waiting for entry conditions</p>';
        return;
      }
      const display = Array.isArray(data) ? data : (data.signals || data);
      el.innerHTML = '<pre style="font-size:12px;white-space:pre-wrap;color:var(--text-secondary);background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:600px;overflow-y:auto">' + 
        JSON.stringify(display, null, 2).replace(/</g, '&lt;') + '</pre>';
    } catch (e) {
      const el = byId('strategy-panel');
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">Failed to load strategy: ' + e.message + '</p>';
    }
  },
};
document.addEventListener('DOMContentLoaded', () => { Logs.init(); if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 200); });
