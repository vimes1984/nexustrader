/**
 * assets.js — Assets Manager tab: ticker listing, activation, exchange status
 */
const Assets = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'assets') this.refresh();
    });
    byId('btn-add-asset')?.addEventListener('click', () => this.showAddForm());
    byId('btn-refresh-exchange')?.addEventListener('click', () => this.checkExchange());
  },

  async refresh() {
    await Promise.all([this.loadAssets(), this.checkExchange()]);
  },

  // ACTUAL API: [{ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling, brains}]
  async loadAssets() {
    try {
      const data = await API.assets();
      const tbody = byId('assets-tbody');
      if (!tbody) return;
      if (!Array.isArray(data) || data.length === 0) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-secondary);text-align:center">No assets configured</td></tr>';
        return;
      }
      tbody.innerHTML = data.map(a =>
        '<tr>' +
          '<td><b>' + (a.ticker || '?') + '</b></td>' +
          '<td>' + (a.ticker || '?') + '</td>' +
          '<td><span style="color:' + (a.is_active ? 'var(--neon-green)' : 'var(--text-secondary)') + '">' + (a.is_active ? 'Active' : 'Inactive') + '</span></td>' +
          '<td style="font-size:12px;color:var(--text-secondary)">TP:' + (a.tp_multiplier || '-') + ' SL:' + (a.sl_multiplier || '-') + '</td>' +
          '<td>' +
            '<button class="btn btn-sm" onclick="Assets.toggleAsset(\'' + a.ticker + '\',' + (!a.is_active) + ')">' + (a.is_active ? 'Deactivate' : 'Activate') + '</button> ' +
            '<button class="btn btn-sm btn-danger" onclick="Assets.deleteAsset(\'' + a.ticker + '\')">Remove</button>' +
          '</td>' +
        '</tr>'
      ).join('');
    } catch (e) {
      App.toast('Failed to load assets: ' + e.message, 'error');
    }
  },

  showAddForm() {
    const ticker = prompt('Ticker symbol (e.g., ADA-USD):');
    if (!ticker) return;
    this.saveAsset({ ticker: ticker, is_active: true });
  },

  async saveAsset(data) {
    if (!data || !data.ticker) return App.toast('Ticker required', 'error');
    try {
      await API.saveAsset(data);
      App.toast('Asset "' + data.ticker + '" saved', 'success');
      this.loadAssets();
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },

  async toggleAsset(ticker, active) {
    try {
      await API.saveAsset({ ticker: ticker, is_active: active });
      App.toast(ticker + ' ' + (active ? 'activated' : 'deactivated'), 'success');
      this.loadAssets();
    } catch (e) {
      App.toast('Toggle failed: ' + e.message, 'error');
    }
  },

  async deleteAsset(ticker) {
    if (!confirm('Remove "' + ticker + '" from tracking?')) return;
    try {
      await API.deleteAsset(ticker);
      App.toast('"' + ticker + '" removed', 'success');
      this.loadAssets();
    } catch (e) {
      App.toast('Delete failed: ' + e.message, 'error');
    }
  },

  async checkExchange() {
    try {
      const data = await API.exchangeStatus();
      const el = byId('exchange-status');
      if (!el) return;
      if (data.connected) {
        el.innerHTML = '<span style="color:var(--neon-green)">● Connected to ' + (data.exchange || 'Kraken') + '</span>';
      } else {
        el.innerHTML = '<span style="color:var(--neon-red)">● Disconnected' + (data.error ? ': ' + data.error.slice(0, 60) : '') + '</span>';
      }
    } catch (e) { /* silent */ }
  },
};
document.addEventListener('DOMContentLoaded', () => { Assets.init(); if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 200); });
