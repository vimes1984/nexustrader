/**
 * neural.js — Training Tab: brain management, neural architecture, historical training
 */
const Neural = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'neural') this.refresh();
    });
    byId('btn-train-brain')?.addEventListener('click', () => this.trainBrain());
    byId('btn-run-training')?.addEventListener('click', () => this.runTraining());
    byId('btn-run-nn-tests')?.addEventListener('click', () => this.runNnTests());
    byId('btn-save-arch')?.addEventListener('click', () => this.saveArchitecture());
  },

  async refresh() {
    await Promise.all([this.loadBrains(), this.loadArchitecture()]);
  },

  async loadBrains() {
    try {
      const data = await API.brains();
      const container = byId('neural-brains-list');
      if (!container) return;
      // API returns {brains: [...]} or flat array
      const brains = data.brains || data || [];
      if (!brains || !brains.length) {
        container.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:20px">No brains configured — train your first brain to get started</p>';
        return;
      }
      container.innerHTML = brains.map(b => {
        const name = b.name || b.id || b.ticker || 'Unknown';
        const ticker = b.ticker || 'BTC-USD';
        return '<div class="glass-panel" style="padding:12px;margin-bottom:8px">' +
          '<div style="display:flex;justify-content:space-between;align-items:center">' +
            '<div>' +
              '<b>' + name + '</b>' +
              '<span style="color:var(--text-secondary);margin-left:8px;font-size:11px">' + ticker + '</span>' +
            '</div>' +
            '<div style="display:flex;gap:8px">' +
              '<button class="btn btn-sm activate-brain-btn" data-ticker="' + ticker + '" data-name="' + name + '">Activate</button>' +
              '<button class="btn btn-sm btn-danger delete-brain-btn" data-name="' + name + '">Delete</button>' +
            '</div>' +
          '</div>' +
          '<div style="font-size:10px;color:var(--text-secondary);margin-top:4px">' +
            'Architecture: ' + (b.arch || 'PolicyNetwork') + ' | LR: ' + (b.lr || '0.01') + ' | Episodes: ' + (b.episodes || 0) +
          '</div>' +
        '</div>';
      }).join('');
      // Delegate click handlers
      container.querySelectorAll('.activate-brain-btn').forEach(btn => {
        btn.addEventListener('click', () => this.activateBrain(btn.dataset.ticker, btn.dataset.name));
      });
      container.querySelectorAll('.delete-brain-btn').forEach(btn => {
        btn.addEventListener('click', () => this.deleteBrain(btn.dataset.name));
      });
    } catch (e) {
      App.toast('Failed to load brains: ' + e.message, 'error');
    }
  },

  async loadArchitecture() {
    try {
      const data = await API.nnArchitecture();
      // API returns {architecture, hidden_dim, hidden_layers, learning_rate, dropout, optimizer}
      if (!data) return;
      const archEl = byId('arch-type');
      if (archEl) archEl.value = data.architecture || data.type || 'mlp';
      setElVal('arch-hidden-dim', data.hidden_dim || 12);
      setElVal('arch-hidden-layers', data.hidden_layers || 1);
      setElVal('arch-lr', data.learning_rate || 0.01);
      setElVal('arch-dropout', data.dropout || 0.0);
      const optEl = byId('arch-optimizer');
      if (optEl) optEl.value = data.optimizer || 'Adam';
    } catch (e) {
      const el = byId('nn-arch-form');
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">Failed to load architecture: ' + e.message + '</p>';
    }
  },

  async trainBrain() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    App.toast('Training brain for ' + ticker + '...', 'info');
    try {
      await API.trainBrain(ticker);
      App.toast('Brain trained for ' + ticker, 'success');
      this.loadBrains();
    } catch (e) { App.toast('Training failed: ' + e.message, 'error'); }
  },

  async activateBrain(ticker, name) {
    try {
      await API.activateBrain(ticker, name);
      App.toast('Brain "' + name + '" activated for ' + ticker, 'success');
    } catch (e) { App.toast('Activation failed: ' + e.message, 'error'); }
  },

  async deleteBrain(name) {
    if (!window.confirm('Delete brain "' + name + '"?')) return;
    try {
      await API.deleteBrain(name);
      App.toast('Brain "' + name + '" deleted', 'success');
      this.loadBrains();
    } catch (e) { App.toast('Delete failed: ' + e.message, 'error'); }
  },

  async runTraining() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    const daysStr = window.prompt('Days of history?', '30');
    const days = parseInt(daysStr) || 30;
    const epochsStr = window.prompt('Training epochs?', '20');
    const epochs = parseInt(epochsStr) || 20;
    App.toast('Starting ' + days + 'd training for ' + ticker + '...', 'info');
    try {
      const r = await API.runTraining(ticker, days, epochs);
      App.toast('Training completed: ' + (r.message || 'done'), 'success');
      this.loadBrains();
    } catch (e) { App.toast('Training failed: ' + e.message, 'error'); }
  },

  async runNnTests() {
    App.toast('Running NN tests...', 'info');
    try {
      const r = await API.runNnTests();
      App.toast(r.message || 'Tests complete', 'success');
    } catch (e) { App.toast('NN tests failed: ' + e.message, 'error'); }
  },

  async saveArchitecture() {
    try {
      const data = {
        type: byId('arch-type')?.value || 'mlp',
        hidden_dim: parseInt(byId('arch-hidden-dim')?.value) || 12,
        hidden_layers: parseInt(byId('arch-hidden-layers')?.value) || 1,
        learning_rate: parseFloat(byId('arch-lr')?.value) || 0.01,
        dropout: parseFloat(byId('arch-dropout')?.value) || 0,
        optimizer: byId('arch-optimizer')?.value || 'Adam',
      };
      await API.setNnArchitecture(data);
      App.toast('Architecture saved', 'success');
    } catch (e) { App.toast('Save failed: ' + e.message, 'error'); }
  },
};

// Helper: set element value safely
function setElVal(id, val) {
  const el = byId(id);
  if (el) el.value = val ?? '';
}

document.addEventListener('DOMContentLoaded', () => { Neural.init(); if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 200); });
