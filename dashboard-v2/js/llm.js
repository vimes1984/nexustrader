/**
 * llm.js v3.2 — LLM tab: status, test, sentiment, regime, config
 */
const LLM = {
  _escape(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  },

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
        const connected = data?.server_connected;
        statusEl.textContent = connected ? '✅ CONNECTED' : '❌ DISCONNECTED';
        statusEl.style.color = connected ? 'var(--neon-green)' : 'var(--neon-red)';
      }
      const modelEl = byId('llm-status-model');
      if (modelEl) modelEl.textContent = data?.model || 'Llama-3.2-3B (fine-tuned)';
      const speedEl = byId('llm-status-speed');
      if (speedEl && data?.speed_toks) speedEl.textContent = data.speed_toks + ' tok/s';
      if (data?.last_sentiment) {
        const s = data.last_sentiment;
        const dirEl = byId('llm-sentiment-dir');
        const dir = s.direction || s.sentiment || s.label || 'neutral';
        if (dirEl) dirEl.textContent = String(dir).toUpperCase();
        const scoreEl = byId('llm-sentiment-score');
        const score = Number(s.sentiment_score || s.score || s.confidence || 0);
        if (scoreEl) scoreEl.textContent = score.toFixed(4);
      }
      // Show LLM server URL in status
      if (data?.llama_server_url || data?.server_url) {
        const url = this._escape(data.llama_server_url || data.server_url || '');
        var serverUrlEl = byId('llm-server-url');
        if (!serverUrlEl) {
          var statusContainer = byId('llm-status-text')?.parentElement;
          if (statusContainer) {
            var urlDiv = document.createElement('div');
            urlDiv.id = 'llm-server-url';
            urlDiv.style.cssText = 'font-size:10px;margin-top:4px;color:var(--text-muted);word-break:break-all';
            urlDiv.textContent = 'Server: ' + url;
            statusContainer.appendChild(urlDiv);
          }
        } else {
          serverUrlEl.textContent = 'Server: ' + url;
        }
      }
    } catch(e) { /* LLM server may not be running */ }
  },

  async loadConfig() {
    try {
      const data = await API.llmConfig();
      if (data?.llama_server_url) {
        try {
          const u = new URL(data.llama_server_url);
          setInput('llm-host', u.hostname);
          setInput('llm-port', u.port || '8080');
        } catch(e) {}
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
      if (el) el.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto;color:var(--text-primary);line-height:1.6">' + this._escape(text) + '</pre>';
      App.toast('LLM test complete ✅', 'success');
    } catch(e) {
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">❌ LLM test failed: ' + this._escape(e.message) + '</p>';
      App.toast('LLM test failed: ' + e.message, 'error');
    }
  },

  async sentiment() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    const el = byId('llm-result'); if (el) el.innerHTML = '<p style="color:var(--text-muted)">⏳ Analyzing sentiment for ' + this._escape(ticker) + '...</p>';
    App.toast('Analyzing sentiment for ' + ticker + '...', 'info');
    try {
      const data = await API.llmSentiment(ticker);
      if (el) el.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto;color:var(--text-primary)">' + this._escape(JSON.stringify(data,null,2)) + '</pre>';
      App.toast('Sentiment analysis complete', 'success');
    } catch(e) {
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">❌ Sentiment failed: ' + this._escape(e.message) + '</p>';
      App.toast('Sentiment failed: ' + e.message, 'error');
    }
  },

  async regime() {
    const ticker = App.state.activeTicker || 'BTC-USD';
    const el = byId('llm-result'); if (el) el.innerHTML = '<p style="color:var(--text-muted)">⏳ Detecting regime for ' + this._escape(ticker) + '...</p>';
    App.toast('Detecting regime for ' + ticker + '...', 'info');
    try {
      const data = await API.llmRegime(ticker);
      if (el) el.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto;color:var(--text-primary)">' + this._escape(JSON.stringify(data,null,2)) + '</pre>';
      App.toast('Regime detection complete', 'success');
    } catch(e) {
      if (el) el.innerHTML = '<p style="color:var(--neon-red)">❌ Regime detection failed: ' + this._escape(e.message) + '</p>';
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

(function() { var fn = function() { LLM.init(); try { if (typeof lucide !== 'undefined' && lucide?.createIcons) lucide.createIcons(); } catch(e) {} }; if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); })();
