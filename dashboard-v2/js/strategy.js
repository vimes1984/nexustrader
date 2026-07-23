/**
 * strategy.js v3.2 — Strategy signal monitor tab
 */
const Strategy = {
  _escape(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  },

  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'strategy') this.load(); });
    byId('btn-refresh-strategy')?.addEventListener('click', () => this.load());
  },

  async load() {
    const panel = byId('strategy-panel'); if (!panel) return;
    panel.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px">Loading signals...</p>';
    try {
      const data = await API.strategyStatus();
      const raw = data?.signals || data?.strategies || data || {};
      const signals = Array.isArray(raw) ? raw : Object.entries(raw).map(([ticker, v]) => (typeof v === 'object' ? { name: ticker, ticker, ...v } : { name: ticker, ticker, signal: v }));
      if (!signals.length) {
        panel.innerHTML = '<div class="glass-panel" style="padding:20px;text-align:center"><p style="color:var(--text-muted);margin-bottom:8px">No active signals</p><p style="font-size:11px;color:var(--text-secondary)">The bot is accumulating data before strategies can fire. Check back in a few minutes.</p></div>';
        return;
      }
      panel.innerHTML = signals.map(s => {
        const sig = Number(s.signal || 0);
        const dir = sig >= 0 ? '▲' : '▼';
        const clr = sig >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        const name = this._escape(s.name || s.strategy || s.id || 'Unknown');
        const ticker = this._escape(s.ticker || s.symbol || '');
        const rawDetails = s.details || '';
        const details = rawDetails ? this._escape(rawDetails.length > 200 ? rawDetails.substring(0, 200) + '...' : rawDetails) : '';
        return `<div class="glass-panel" style="padding:12px 14px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <span style="font-weight:700;font-size:13px">${name}</span>
              <span style="font-size:10px;color:var(--text-muted);margin-left:8px">${ticker}</span>
            </div>
            <span style="font-weight:700;font-size:14px;font-family:var(--font-mono);color:${clr}">${dir} ${Math.abs(sig).toFixed(4)}</span>
          </div>
          ${s.confidence != null ? `<div style="margin-top:6px;font-size:10px;color:var(--text-secondary)">Confidence: ${(Number(s.confidence)*100).toFixed(1)}%</div>` : ''}
          ${details ? `<div style="margin-top:4px;font-size:10px;color:var(--text-muted)">${details}</div>` : ''}
        </div>`;
      }).join('');
    } catch(e) {
      panel.innerHTML = '<div class="glass-panel" style="padding:20px;text-align:center;color:var(--neon-red)">❌ Failed to load strategy signals: ' + this._escape(e.message) + '</div>';
    }
  },
};

document.addEventListener('DOMContentLoaded', () => Strategy.init());
