/**
 * logs.js v3.2 — System logs tab
 */
const Logs = {
  _escape(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  },

  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'logs') this.load(); });
    byId('btn-refresh-logs')?.addEventListener('click', () => this.load());
  },

  async load() {
    const el = byId('system-logs'); if (!el) return;
    showSkeleton(el, 3);

    try {
      const data = await API.systemLogs(1000);
      let lines = [];

      if (typeof data === 'string') {
        lines = data.split('\n').filter(Boolean);
      } else if (Array.isArray(data)) {
        lines = data.map(l => (typeof l === 'string') ? l : (l.message || l.text || l.msg || JSON.stringify(l)));
      } else if (data?.logs && Array.isArray(data.logs)) {
        lines = data.logs.map(function(l) {
          if (typeof l === 'string') return l;
          if (l && typeof l === 'object') {
            // Try common log field names
            var msg = l.message || l.text || l.msg || l.log || l.entry || '';
            if (msg) {
              var ts = l.timestamp || l.time || l.created || '';
              if (ts) {
                var tsN = Number(ts);
                if (!isNaN(tsN)) {
                  if (tsN > 1e12) tsN = Math.floor(tsN / 1000);
                  ts = new Date(tsN * 1000).toISOString().replace('T',' ').substring(0,19);
                } else {
                  ts = String(ts);
                }
                return '[' + ts + '] ' + msg;
              }
              return msg;
            }
            var level = l.level || l.severity || '';
            if (level) return '[' + level.toUpperCase() + '] ' + JSON.stringify(l);
            return JSON.stringify(l);
          }
          return String(l);
        });
      } else if (typeof data === 'object' && data !== null) {
        lines = Object.entries(data).map(([k,v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`);
      }

      if (!lines.length) {
        // Show total count if available even with empty lines
        if (data && data.total != null && Number(data.total) > 0) {
          el.innerHTML = '<div style="padding:10px;text-align:center;font-size:11px;color:var(--text-muted)">' + Number(data.total) + ' total log entries (filtered view)</div>';
          return;
        }
        el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">No log entries yet</div>';
        return;
      }

      // Show total log count header
      let headerHtml = '';
      if (data && data.total != null) {
        headerHtml = '<div style="padding:6px 8px;font-size:10px;color:var(--text-muted);border-bottom:1px solid rgba(255,255,255,0.04);text-align:right">' + Number(data.total) + ' total · ' + lines.length + ' shown</div>';
      }

      el.innerHTML = headerHtml + lines.map(l => {
        let cls = '';
        const lower = l.toLowerCase();
        if (lower.includes('error') || lower.includes('critical') || lower.includes('traceback')) cls = 'color:var(--neon-red)';
        else if (lower.includes('warn')) cls = 'color:var(--neon-yellow)';
        else if (lower.includes('info') || lower.includes('success')) cls = 'color:var(--neon-green)';
        return `<div style="font-size:10px;padding:3px 6px;border-bottom:1px solid rgba(255,255,255,0.02);${cls};white-space:pre-wrap;word-break:break-all">${this._escape(l)}</div>`;
      }).join('');
    } catch(e) {
      el.innerHTML = `<div style="padding:20px;text-align:center;color:var(--neon-red)">❌ Failed to load logs: ${this._escape(e.message)}</div>`;
    }
  },
};

document.addEventListener('DOMContentLoaded', () => Logs.init());
