/**
 * llm.js — LLM Management tab: LLaMA status, test, sentiment, regime, config
 */
const LLM = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'llm') this.refresh();
    });
    byId('btn-llm-test')?.addEventListener('click', () => this.test());
    byId('btn-llm-sentiment')?.addEventListener('click', () => this.sentiment());
    byId('btn-llm-regime')?.addEventListener('click', () => this.regime());
    byId('btn-llm-save-config')?.addEventListener('click', () => this.saveConfig());
  },

  async refresh() {
    await Promise.all([this.loadStatus(), this.loadConfig()]);
  },

  async loadStatus() {
    try {
      const data = await API.llmStatus();
      const el = byId('llm-status-card');
      if (!el) return;
      if (data.connected) {
        el.innerHTML = `
          <div style="color:var(--neon-green);font-weight:600;margin-bottom:8px">● LLaMA Connected</div>
          <div style="font-size:12px;color:var(--text-secondary)">
            Model: ${data.model || 'Unknown'}<br>
            Tokens/sec: ${data.tokens_per_sec || 'N/A'}<br>
            Provider: ${data.provider || 'local'}
          </div>`;
      } else {
        el.innerHTML = `
          <div style="color:var(--neon-red);font-weight:600;margin-bottom:8px">● LLaMA Disconnected</div>
          <div style="font-size:12px;color:var(--text-secondary)">${data.error || 'Server unreachable'}</div>`;
      }
    } catch (e) {
      App.toast('Failed to load LLM status', 'error');
    }
  },

  async loadConfig() {
    try {
      const data = await API.llmConfig();
      // API returns: {server_url, model, enabled, fallback_to_openclaw}
      if (data.server_url) {
        try { const u = new URL(data.server_url); setInput('llm-host', u.hostname); setInput('llm-port', u.port || '8080'); } catch(e) {}
      }
      setInput('llm-model-name', data.model);
    } catch (e) { /* silent */ }
  },

  async test() {
    const prompt = prompt('Test prompt:', 'What is the current market sentiment?');
    if (!prompt) return;
    App.toast('Querying LLM...', 'info');
    try {
      const data = await API.llmTest({ prompt, role: 'analyst' });
      const resultEl = byId('llm-result');
      if (resultEl) resultEl.innerHTML = `<pre style="white-space:pre-wrap;font-size:12px">${data.response || data.text || JSON.stringify(data, null, 2)}</pre>`;
      App.toast('LLM response received', 'success');
    } catch (e) {
      App.toast('LLM test failed: ' + e.message, 'error');
    }
  },

  async sentiment() {
    const ticker = App.state.activeTicker;
    App.toast(`Analyzing sentiment for ${ticker}...`, 'info');
    try {
      const data = await API.llmSentiment(ticker);
      const resultEl = byId('llm-result');
      if (resultEl) resultEl.innerHTML = `<pre style="white-space:pre-wrap;font-size:12px">${JSON.stringify(data, null, 2)}</pre>`;
      App.toast('Sentiment analysis complete', 'success');
    } catch (e) {
      App.toast('Sentiment analysis failed: ' + e.message, 'error');
    }
  },

  async regime() {
    const ticker = App.state.activeTicker;
    App.toast(`Detecting regime for ${ticker}...`, 'info');
    try {
      const data = await API.llmRegime(ticker);
      const resultEl = byId('llm-result');
      if (resultEl) resultEl.innerHTML = `<pre style="white-space:pre-wrap;font-size:12px">${JSON.stringify(data, null, 2)}</pre>`;
      App.toast('Regime detection complete', 'success');
    } catch (e) {
      App.toast('Regime detection failed: ' + e.message, 'error');
    }
  },

  async saveConfig() {
    try {
      const data = {
        host: byId('llm-host')?.value,
        port: parseInt(byId('llm-port')?.value) || 8080,
        model: byId('llm-model-name')?.value,
        temperature: parseFloat(byId('llm-temperature')?.value) || 0.7,
      };
      await API.setLlmConfig(data);
      App.toast('LLM config saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },
};
document.addEventListener('DOMContentLoaded', () => LLM.init());
