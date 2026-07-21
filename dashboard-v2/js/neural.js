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
      if (!data.brains || data.brains.length === 0) {
        container.innerHTML = '<p style="color:var(--text-secondary)">No brains configured</p>';
        return;
      }
      container.innerHTML = data.brains.map(b => `
        <div class="glass-panel" style="padding:12px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <b>${b.name || b.ticker}</b>
              <span style="color:var(--text-secondary);margin-left:8px;font-size:11px">${b.ticker || ''}</span>
            </div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-sm" onclick="Neural.activateBrain('${b.ticker || 'BTC-USD'}','${b.name}')">Activate</button>
              <button class="btn btn-sm btn-danger" onclick="Neural.deleteBrain('${b.name}')">Delete</button>
            </div>
          </div>
          <div style="font-size:10px;color:var(--text-secondary);margin-top:4px">
            Architecture: ${b.arch || 'PolicyNetwork'} | LR: ${b.lr || '0.01'} | Episodes: ${b.episodes || 0}
          </div>
        </div>
      `).join('');
    } catch (e) {
      App.toast('Failed to load brains: ' + e.message, 'error');
    }
  },

  async loadArchitecture() {
    try {
      const data = await API.nnArchitecture();
      const form = byId('nn-arch-form');
      if (!form) return;
      const arch = data.architecture || data.type || 'mlp';
      byId('arch-type').value = arch;
      byId('arch-hidden-dim').value = data.hidden_dim || 12;
      byId('arch-hidden-layers').value = data.hidden_layers || 1;
      byId('arch-lr').value = data.learning_rate || 0.01;
      byId('arch-dropout').value = data.dropout || 0.0;
      byId('arch-optimizer').value = data.optimizer || 'Adam';
    } catch (e) {
      App.toast('Failed to load architecture: ' + e.message, 'error');
    }
  },

  async trainBrain() {
    const ticker = App.state.activeTicker;
    App.toast(`Training brain for ${ticker}...`, 'info');
    try {
      await API.trainBrain(ticker);
      App.toast(`Brain trained for ${ticker}`, 'success');
    } catch (e) {
      App.toast('Training failed: ' + e.message, 'error');
    }
  },

  async activateBrain(ticker, name) {
    try {
      await API.activateBrain(ticker, name);
      App.toast(`Brain "${name}" activated for ${ticker}`, 'success');
    } catch (e) {
      App.toast('Activation failed: ' + e.message, 'error');
    }
  },

  async deleteBrain(name) {
    if (!confirm(`Delete brain "${name}"?`)) return;
    try {
      await API.deleteBrain(name);
      App.toast(`Brain "${name}" deleted`, 'success');
      this.loadBrains();
    } catch (e) {
      App.toast('Delete failed: ' + e.message, 'error');
    }
  },

  async runTraining() {
    const ticker = App.state.activeTicker;
    const days = parseInt(prompt('Days of history?', '30')) || 30;
    const epochs = parseInt(prompt('Training epochs?', '20')) || 20;
    App.toast(`Starting ${days}d training for ${ticker}...`, 'info');
    try {
      const r = await API.runTraining(ticker, days, epochs);
      App.toast(`Training started: ${r.message}`, 'success');
    } catch (e) {
      App.toast('Training failed: ' + e.message, 'error');
    }
  },

  async runNnTests() {
    App.toast('Running NN tests...', 'info');
    try {
      const r = await API.runNnTests();
      App.toast(r.message || 'Tests complete', 'success');
    } catch (e) {
      App.toast('NN tests failed: ' + e.message, 'error');
    }
  },

  async saveArchitecture() {
    try {
      const data = {
        type: byId('arch-type').value,
        hidden_dim: parseInt(byId('arch-hidden-dim').value),
        hidden_layers: parseInt(byId('arch-hidden-layers').value),
        learning_rate: parseFloat(byId('arch-lr').value),
        dropout: parseFloat(byId('arch-dropout').value),
        optimizer: byId('arch-optimizer').value,
      };
      await API.setNnArchitecture(data);
      App.toast('Architecture saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },
};
document.addEventListener('DOMContentLoaded', () => Neural.init());
