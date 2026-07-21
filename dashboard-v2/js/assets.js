/**
 * assets.js v3 — Asset management tab
 */
const Assets = {
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
      const tickers = Array.isArray(data) ? data : (data?.tickers || data?.assets || []);
      if (!tickers.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--text-muted)">No tracked assets</td></tr>';
        return;
      }
      tbody.innerHTML = tickers.map(t => {
        const ticker = typeof t === 'string' ? t : (t.ticker || t.symbol || t.name || '?');
        const name = t.name || ticker;
        const isActive = t.is_active !== false;
        const added = t.added_at || t.created || '';
        const addedDate = added ? new Date(added).toLocaleDateString() : '—';
        return `<tr>
          <td style="font-weight:600">${ticker}</td>
          <td style="color:var(--text-secondary)">${name}</td>
          <td><span style="color:${isActive?'var(--neon-green)':'var(--neon-red)'};font-size:11px">${isActive ? '● Active' : '○ Inactive'}</span></td>
          <td style="color:var(--text-muted);font-size:10px">${addedDate}</td>
          <td>
            <button class="btn btn-sm" data-action="toggle" data-ticker="${ticker}" data-active="${isActive}">${isActive ? 'Deactivate' : 'Activate'}</button>
            <button class="btn btn-sm btn-danger" data-action="remove" data-ticker="${ticker}">Remove</button>
          </td>
        </tr>`;
      }).join('');
    } catch(e) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--neon-red)">Failed to load assets</td></tr>';
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
      if (currentlyActive) {
        await API.saveSetting('ticker_active_' + ticker, '0');
      } else {
        await API.saveSetting('ticker_active_' + ticker, '1');
      }
      App.toast(ticker + ' ' + (currentlyActive ? 'deactivated' : 'activated'), 'success');
      this.load();
    } catch(e) { App.toast('Toggle failed: ' + e.message, 'error'); }
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

document.addEventListener('DOMContentLoaded', () => Assets.init());
