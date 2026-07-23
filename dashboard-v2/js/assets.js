/**
 * assets.js v3.2 — Asset management tab
 */
const Assets = {
  _escape(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  },

  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'assets') this.load(); });
    byId('btn-add-asset')?.addEventListener('click', () => this.addAsset());
    byId('btn-refresh-exchange')?.addEventListener('click', () => this.checkExchange());
    byId('assets-tbody')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (btn) {
        const ticker = btn.dataset.ticker;
        if (btn.dataset.action === 'remove') this.removeAsset(ticker);
        else if (btn.dataset.action === 'toggle') this.toggleAsset(ticker, btn.dataset.active === 'true');
      }
    });
  },

  async load() {
    const tbody = byId('assets-tbody'); if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--text-muted)">Loading...</td></tr>';
    try {
      const data = await API.assetList();
      let tickers = Array.isArray(data) ? data : (data?.tickers || data?.assets || []);
      // Handle string (space/comma separated) ticker list
      if (typeof tickers === 'string') {
        tickers = tickers.split(/[,\s]+/).filter(Boolean);
      }
      // Guard against non-array types
      if (!Array.isArray(tickers)) tickers = [];
      if (!tickers.length) {
        tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="empty-state-icon" aria-hidden="true">📦</div><div class="empty-state-title">No tracked assets</div><div class="empty-state-desc">Add your first ticker symbol to start tracking assets.</div></div></td></tr>';
        return;
      }
      // Helper to normalize timestamp
      function fmtDate(v) {
        if (!v) return '—';
        var n = Number(v);
        // If it's a numeric timestamp
        if (!isNaN(n)) {
          if (n > 1e12) n = Math.floor(n / 1000); // ms to s
          if (n > 1e9 && n < 1e11) return new Date(n * 1000).toLocaleDateString();
        }
        var d = new Date(v);
        return isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
      }

      tbody.innerHTML = tickers.map(t => {
        const ticker = typeof t === 'string' ? t : (t.ticker || t.symbol || t.name || '?');
        const name = t.name || ticker;
        const isActive = t.is_active !== false;
        const addedDate = fmtDate(t.added_at || t.created || t.added || '');
        return `<tr>
          <td style="font-weight:600">${this._escape(ticker)}</td>
          <td style="color:var(--text-secondary)">${this._escape(name)}</td>
          <td><span style="color:${isActive?'var(--neon-green)':'var(--neon-red)'};font-size:11px">${isActive ? '● Active' : '○ Inactive'}</span></td>
          <td style="color:var(--text-muted);font-size:10px">${addedDate}</td>
          <td>
            <button class="btn btn-sm" data-action="toggle" data-ticker="${this._escape(ticker)}" data-active="${isActive}">${isActive ? 'Deactivate' : 'Activate'}</button>
            <button class="btn btn-sm btn-danger" data-action="remove" data-ticker="${this._escape(ticker)}">Remove</button>
          </td>
        </tr>`;
      }).join('');
    } catch(e) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--neon-red)">Failed to load assets: ' + this._escape(e.message) + '</td></tr>';
    }
  },

  async addAsset() {
    const ticker = window.prompt('Ticker symbol (e.g., ADA-USD):');
    if (!ticker) return;
    App.toast('Adding ' + ticker + '...', 'info');
    try {
      await API.addAsset(ticker);
      App.toast(ticker + ' added', 'success');
      this.load();
    } catch(e) { App.toast('Add failed: ' + e.message, 'error'); }
  },

  async removeAsset(ticker) {
    if (!confirm('Remove ' + ticker + ' from tracking?')) return;
    try {
      await API.removeAsset(ticker);
      App.toast(ticker + ' removed', 'success');
      this.load();
    } catch(e) { App.toast('Remove failed: ' + e.message, 'error'); }
  },

  async toggleAsset(ticker, currentlyActive) {
    try {
      const newState = currentlyActive ? '0' : '1';
      await API.saveSetting('ticker_active_' + ticker, newState);
      App.toast(ticker + ' ' + (currentlyActive ? 'deactivated' : 'activated'), 'success');
      // Re-fetch asset list to reflect new state
      await this.load();
    } catch(e) { App.toast('Toggle failed: ' + (e.message || 'Unknown error'), 'error'); }
  },

  async checkExchange() {
    App.toast('Checking exchange...', 'info');
    try {
      const data = await API.checkExchange();
      const el = byId('exchange-status');
      if (el) el.textContent = data.status || 'Checked';
      App.toast('Exchange check: ' + (data.status || 'OK'), 'success');
      this.load();
    } catch(e) { App.toast('Exchange check failed: ' + e.message, 'error'); }
  },
};

(function() { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function() { Assets.init(); }); else Assets.init(); })();
