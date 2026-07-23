/**
 * neural.js v3.2 — Training tab: brains list, historical pipeline, architecture
 */
const Neural = {
  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'neural') this.refresh(); });
    byId('btn-train-brain')?.addEventListener('click', () => this.trainBrain());
    byId('btn-run-training')?.addEventListener('click', () => this.runTraining());
    byId('btn-save-arch')?.addEventListener('click', () => this.saveArch());
    byId('btn-run-nn-tests')?.addEventListener('click', () => this.runTests());

    // Brains list delegated clicks
    byId('neural-brains-list')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (btn) {
        const action = btn.dataset.action;
        const ticker = btn.dataset.ticker;
        if (action === 'train') this.trainBrain(ticker);
        else if (action === 'activate') this.activateBrain(ticker);
      }
    });
  },

  async refresh() {
    await this.loadBrains();
    this.loadArch();
  },

  async loadBrains() {
    const el = byId('neural-brains-list'); if (!el) return;
    showSkeleton(el, 3);
    try {
      const data = await API.brains();
      if (!data?.brains?.length) {
        showEmptyState(el, { icon: '🧠', title: 'No trained brains', desc: 'Run the historical training pipeline to create policy networks for your tickers.' });
        return;
      }
      el.innerHTML = data.brains.map(b => `
        <div class="glass-panel" style="padding:10px 12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
          <div>
            <span style="font-weight:600;font-size:13px">${this._escape(b.ticker || b.name || 'Unknown')}</span>
            <span style="font-size:10px;color:var(--text-muted);margin-left:8px">${b.action_dim || b.dim || '?'} actions</span>
            ${b.active ? '<span style="font-size:10px;color:var(--neon-green);margin-left:6px">● Active</span>' : ''}
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-sm" data-action="train" data-ticker="${this._escape(b.ticker || '')}">🔄 Train</button>
            ${!b.active ? `<button class="btn btn-sm btn-primary" data-action="activate" data-ticker="${this._escape(b.ticker || '')}">Activate</button>` : ''}
          </div>
        </div>`).join('');
    } catch(e) {
      showEmptyState(el, { icon: '❌', title: 'Connection error', desc: 'Could not load brain data from the server.' });
    }
  },

  async trainBrain(ticker) {
    const target = ticker || (App.state && App.state.activeTicker) || 'BTC-USD';
    App.toast('Training brain for ' + target + '...', 'info');
    try {
      const data = await API.trainBrain(target);
      App.toast(data.message || 'Training started for ' + target, 'success');
      this.loadBrains();
    } catch(e) { App.toast('Train failed: ' + e.message, 'error'); }
  },

  async activateBrain(ticker) {
    try {
      await API.setAutoSwitch({ ticker });
      App.toast('Brain activated for ' + ticker, 'success');
      this.loadBrains();
    } catch(e) { App.toast('Activation failed: ' + e.message, 'error'); }
  },

  async runTraining() {
    App.toast('Running historical training pipeline... This may take a minute.', 'info');
    try {
      const data = await API.train();
      App.toast('Training complete: ' + (data.samples || data.message || 'OK'), 'success');
      this.loadBrains();
    } catch(e) { App.toast('Training failed: ' + e.message, 'error'); }
  },

  loadArch() {
    // Mark inputs as loading — set defaults first, then overwrite from API
    setInput('arch-hidden-dim', '12');
    setInput('arch-hidden-layers', '1');
    setInput('arch-lr', '0.01');
    setInput('arch-dropout', '0.0');
    API.brainSpecs().then(data => {
      if (data) {
        setInput('arch-hidden-dim', data.hidden_dim ?? data.hidden ?? '12');
        setInput('arch-hidden-layers', data.hidden_layers ?? data.layers ?? '1');
        setInput('arch-lr', data.learning_rate ?? data.lr ?? '0.01');
        setInput('arch-dropout', data.dropout ?? '0.0');
        const typeEl = byId('arch-type'); if (typeEl) typeEl.value = data.type || 'simple';
        const optEl = byId('arch-optimizer'); if (optEl) optEl.value = data.optimizer || 'Adam';
      }
    }).catch(function(err) {
      // Keep defaults if API fails
      if (document.body.classList.contains('debug')) console.log('[Neural] Arch load failed, using defaults:', err);
    });
  },

  async saveArch() {
    try {
      const data = {
        type: getInput('arch-type'),
        hidden_dim: parseInt(getInput('arch-hidden-dim')) || 12,
        hidden_layers: parseInt(getInput('arch-hidden-layers')) || 1,
        learning_rate: parseFloat(getInput('arch-lr')) || 0.01,
        dropout: parseFloat(getInput('arch-dropout')) || 0,
        optimizer: getInput('arch-optimizer') || 'Adam',
      };
      await API.saveArch(data);
      App.toast('Architecture saved', 'success');
    } catch(e) { App.toast('Save failed: ' + e.message, 'error'); }
  },

  async runTests() {
    App.toast('Running NN tests...', 'info');
    try {
      const data = await API.runNnTests();
      App.toast('Tests: ' + (data.passed || 0) + '/' + (data.total || 0) + ' passed', data.failures ? 'warn' : 'success');
    } catch(e) { App.toast('Tests failed: ' + e.message, 'error'); }
  },

  _escape(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  },
};

(function() { var fn = function() { Neural.init(); try { if (typeof lucide !== 'undefined' && lucide?.createIcons) lucide.createIcons(); } catch(e) {} }; if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); })();
