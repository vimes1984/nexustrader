/**
 * logs.js v3 — System logs tab
 */
const Logs = {
  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'logs') this.load(); });
    byId('btn-refresh-logs')?.addEventListener('click', () => this.load());
  },

  async load() {
    const el = byId('system-logs'); if (!el) return;
    el.innerHTML = '<div class="skeleton skeleton-chart" style="height:300px"></div><div class="skeleton skeleton-text" style="width:95%"></div><div class="skeleton skeleton-text" style="width:70%"></div>';
    try {
      const data = await API.systemLogs(1000);
      let lines = [];

      if (typeof data === 'string') {
        lines = data.split('\n').filter(Boolean);
      } else if (Array.isArray(data)) {
        lines = data.map(l => (typeof l === 'string') ? l : (l.message || l.text || l.msg || JSON.stringify(l)));
      } else if (data?.logs && Array.isArray(data.logs)) {
        lines = data.logs.map(l => (typeof l === 'string') ? l : (l.message || l.text || l.msg || JSON.stringify(l)));
      } else if (typeof data === 'object') {
        lines = Object.entries(data).map(([k,v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`);
      }

      if (!lines.length) {
        el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">No log entries yet</div>';
        return;
      }

      el.innerHTML = lines.map(l => {
        let cls = '';
        const lower = l.toLowerCase();
        if (lower.includes('error') || lower.includes('critical') || lower.includes('traceback')) cls = 'color:var(--neon-red)';
        else if (lower.includes('warn')) cls = 'color:var(--neon-yellow)';
        else if (lower.includes('info') || lower.includes('success')) cls = 'color:var(--neon-green)';
        return `<div style="font-size:10px;padding:3px 6px;border-bottom:1px solid rgba(255,255,255,0.02);${cls};white-space:pre-wrap;word-break:break-all">${l.replace(/</g,'&lt;')}</div>`;
      }).join('');
    } catch(e) {
      el.innerHTML = `<div style="padding:20px;text-align:center;color:var(--neon-red)">❌ Failed to load logs: ${e.message}</div>`;
    }
  },
};

document.addEventListener('DOMContentLoaded', () => Logs.init());
