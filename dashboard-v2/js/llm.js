/**
 * llm.js v3 — LLM tab: status, test, sentiment, regime, config
 */
const LLM = {
  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'llm') this.refresh(); });
    byId('btn-llm-test')?.addEventListener('click', () => this.test());
    byId('btn-llm-sentiment')?.addEventListener('click', () => this.sentiment());
    byId('btn-llm-regime')?.addEventListener('click', () => this.regime());
    byId('btn-llm-save')?.addEventListener('click', () => this.saveConfig());
    byId('btn-llm-refresh')?.addEventListener('click', () => this.refresh());
  },

  async refresh() { await Promise.all([this.loadStatus(), this.loadConfig()]); },

  async loadStatus() {
    try {
      const data = await API.llmStatus();
      const statusEl = byId('llm-status-text');
      if (statusEl) {
        statusEl.textContent = data?.server_connected ? '✅ CONNECTED' : '❌ DISCONNECTED';
        statusEl.style.color = data?.server_connected ? 'var(--neon-green)' : 'var(--neon-red)';
      }
      const modelEl = byId('llm-status-model');
      if (modelEl) modelEl.textContent = data?.model || 'Llama-3.2-3B (fine-tuned)';
      const speedEl = byId('llm-status-speed');
      if (speedEl && data?.speed_toks) speedEl.textContent = data.speed_toks + ' tok/s';
      if (data?.last_sentiment) {
        const s = data.last_sentiment;
        byId('llm-sentiment-dir').textContent = (s.direction || 'neutral').toUpperCase();
        byId('llm-sentiment-score').textContent = (s.sentiment_score || 0).toFixed(4);
      }
    } catch(e) { /* LLM server may not be running */ }
  },

  async loadConfig() {
    try {
      const data = await API.llmConfig();
      if (data?.llama_server_url) {
        try { const u = new URL(data.llama_server_url); setInput('llm-host', u.hostname); setInput('llm-port', u.port || '8080'); } catch(e) {}
      }
      setCheckbox('llm-enabled', data?.enabled || data?.use_local_llama);
      setCheckbox('llm-fallback', data?.llama_fallback_to_openclaw);
    } catch(e) {}
  },

  async test() {
    const userInput = window.prompt('Test prompt:', 'What is the current market sentiment?');
    if (!userInput) return;
    const el = byId('llm-result'); if (el) el.innerHTML = '<p style="color:var(--text-muted)">⏳ Querying LLM...</p>';
    App.toast('Querying LLM...', 'info');
    try {
      const data = await API.llmTest({ prompt: userInput, role: 'analyst' });
      const text = data?.response || data?.text || data?.reply || JSON.stringify(data, null, 2);
      if (el) el.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto;color:var(--text-primary);line-height:1.6">' + text.replace(/</g,'&lt;') + '</pre>';
      App.toast('LLM test complete ✅', 'success');
    } catch(e) {
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">❌ LLM test failed: ' + e.message + '</p>';
      App.toast('LLM test failed: ' + e.message, 'error');
    }
  },

  async sentiment() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    const el = byId('llm-result'); if (el) el.innerHTML = '<p style="color:var(--text-muted)">⏳ Analyzing sentiment for ' + ticker + '...</p>';
    App.toast('Analyzing sentiment for ' + ticker + '...', 'info');
    try {
      const data = await API.llmSentiment(ticker);
      if (el) el.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto;color:var(--text-primary)">' + JSON.stringify(data,null,2).replace(/</g,'&lt;') + '</pre>';
      App.toast('Sentiment analysis complete', 'success');
    } catch(e) {
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">❌ Sentiment failed: ' + e.message + '</p>';
      App.toast('Sentiment failed: ' + e.message, 'error');
    }
  },

  async regime() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    const el = byId('llm-result'); if (el) el.innerHTML = '<p style="color:var(--text-muted)">⏳ Detecting regime for ' + ticker + '...</p>';
    App.toast('Detecting regime for ' + ticker + '...', 'info');
    try {
      const data = await API.llmRegime(ticker);
      if (el) el.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto;color:var(--text-primary)">' + JSON.stringify(data,null,2).replace(/</g,'&lt;') + '</pre>';
      App.toast('Regime detection complete', 'success');
    } catch(e) {
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">❌ Regime detection failed: ' + e.message + '</p>';
      App.toast('Regime detection failed: ' + e.message, 'error');
    }
  },

  async saveConfig() {
    try {
      const host = getInput('llm-host') || '192.168.0.77';
      const port = getInput('llm-port') || '8080';
      const data = {
        server_url: 'http://' + host + ':' + port + '/v1/chat/completions',
        enabled: byId('llm-enabled')?.checked ?? true,
        fallback_to_openclaw: byId('llm-fallback')?.checked ?? true,
      };
      await API.setLlmConfig(data);
      App.toast('LLM config saved', 'success');
    } catch(e) { App.toast('Save failed: ' + e.message, 'error'); }
  },
};

document.addEventListener('DOMContentLoaded', () => { LLM.init(); lucide?.createIcons(); });
