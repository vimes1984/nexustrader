/**
 * llm.js — LLM Management tab: LLaMA status, test, sentiment, regime, config
 */

// Helpers (also in settings.js, safe to redefine)
function setInput(id, val) { const el = byId(id); if (el) el.value = val ?? ''; }
function setCheckbox(id, val) { const el = byId(id); if (el) el.checked = !!val; }

const LLM = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'llm') this.refresh();
    });
    byId('btn-llm-test')?.addEventListener('click', () => this.test());
    byId('btn-llm-sentiment')?.addEventListener('click', () => this.sentiment());
    byId('btn-llm-regime')?.addEventListener('click', () => this.regime());
    byId('btn-llm-save')?.addEventListener('click', () => this.saveConfig());
    byId('btn-llm-refresh')?.addEventListener('click', () => this.refresh());
  },

  async refresh() {
    await Promise.all([this.loadStatus(), this.loadConfig()]);
  },

  async loadStatus() {
    try {
      const data = await API.llmStatus();
      const statusEl = byId('llm-status-text');
      if (statusEl) {
        statusEl.textContent = data.server_connected ? 'CONNECTED' : 'DISCONNECTED';
        statusEl.style.color = data.server_connected ? 'var(--neon-green)' : 'var(--neon-red)';
      }
      const modelEl = byId('llm-status-model');
      if (modelEl) modelEl.textContent = data.model || 'Llama-3.2-3B';
      const speedEl = byId('llm-status-speed');
      if (speedEl && data.speed_toks) speedEl.textContent = data.speed_toks + ' tok/s';
      if (data.last_sentiment) {
        const s = data.last_sentiment;
        const dirEl = byId('llm-sentiment-dir');
        if (dirEl) dirEl.textContent = (s.direction || 'neutral').toUpperCase();
        const scoreEl = byId('llm-sentiment-score');
        if (scoreEl) scoreEl.textContent = (s.sentiment_score || 0).toFixed(4);
      }
    } catch (e) {
      App.toast('Failed to load LLM status', 'error');
    }
  },

  async loadConfig() {
    try {
      const data = await API.llmConfig();
      if (data.llama_server_url) {
        try {
          const u = new URL(data.llama_server_url);
          setInput('llm-host', u.hostname);
          setInput('llm-port', u.port || '8080');
        } catch(e) {}
      } else if (data.endpoint) {
        try {
          const u = new URL(data.endpoint);
          setInput('llm-host', u.hostname);
          setInput('llm-port', u.port || '8080');
        } catch(e) {}
      }
      setCheckbox('llm-enabled', data.enabled || data.use_local_llama);
      setCheckbox('llm-fallback', data.llama_fallback_to_openclaw);
    } catch (e) { /* silent */ }
  },

  async test() {
    // FIX: 'prompt' as variable name shadows window.prompt() — use 'userPrompt'
    const userPrompt = window.prompt('Test prompt:', 'What is the current market sentiment?');
    if (!userPrompt) return;
    const resultEl = byId('llm-result');
    if (resultEl) resultEl.innerHTML = '<p style="color:var(--text-secondary)">⏳ Querying LLM...</p>';
    App.toast('Querying LLM...', 'info');
    try {
      const data = await API.llmTest({ prompt: userPrompt, role: 'analyst' });
      const text = data.response || data.text || data.reply || JSON.stringify(data, null, 2);
      if (resultEl) resultEl.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto">' + text.replace(/</g, '&lt;') + '</pre>';
      App.toast('LLM response received', 'success');
    } catch (e) {
      if (resultEl) resultEl.innerHTML = '<p style="color:var(--neon-red)">LLM test failed: ' + e.message + '</p>';
      App.toast('LLM test failed: ' + e.message, 'error');
    }
  },

  async sentiment() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    const resultEl = byId('llm-result');
    if (resultEl) resultEl.innerHTML = '<p style="color:var(--text-secondary)">⏳ Analyzing sentiment for ' + ticker + '...</p>';
    App.toast('Analyzing sentiment for ' + ticker + '...', 'info');
    try {
      const data = await API.llmSentiment(ticker);
      if (resultEl) resultEl.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto">' + JSON.stringify(data, null, 2).replace(/</g, '&lt;') + '</pre>';
      App.toast('Sentiment analysis complete', 'success');
    } catch (e) {
      if (resultEl) resultEl.innerHTML = '<p style="color:var(--neon-red)">Sentiment failed: ' + e.message + '</p>';
      App.toast('Sentiment analysis failed: ' + e.message, 'error');
    }
  },

  async regime() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    const resultEl = byId('llm-result');
    if (resultEl) resultEl.innerHTML = '<p style="color:var(--text-secondary)">⏳ Detecting regime for ' + ticker + '...</p>';
    App.toast('Detecting regime for ' + ticker + '...', 'info');
    try {
      const data = await API.llmRegime(ticker);
      if (resultEl) resultEl.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto">' + JSON.stringify(data, null, 2).replace(/</g, '&lt;') + '</pre>';
      App.toast('Regime detection complete', 'success');
    } catch (e) {
      if (resultEl) resultEl.innerHTML = '<p style="color:var(--neon-red)">Regime detection failed: ' + e.message + '</p>';
      App.toast('Regime detection failed: ' + e.message, 'error');
    }
  },

  async saveConfig() {
    try {
      const host = byId('llm-host')?.value || '192.168.0.77';
      const port = byId('llm-port')?.value || '8080';
      const server_url = 'http://' + host + ':' + port + '/v1/chat/completions';
      const data = {
        server_url: server_url,
        enabled: byId('llm-enabled')?.checked ?? true,
        fallback_to_openclaw: byId('llm-fallback')?.checked ?? true,
      };
      await API.setLlmConfig(data);
      App.toast('LLM config saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },
};
document.addEventListener('DOMContentLoaded', () => { LLM.init(); if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 200); });
