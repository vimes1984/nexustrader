/**
 * agents.js — Quant Team tab: agent status, triggers, prompt management, LLM config
 */
const Agents = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'agents') this.refresh();
    });
    byId('btn-trigger-all')?.addEventListener('click', () => this.triggerAll());
    byId('btn-refresh-agents')?.addEventListener('click', () => this.refresh());
    byId('btn-save-prompts')?.addEventListener('click', () => this.savePrompts());
    byId('btn-save-agent-llm')?.addEventListener('click', () => this.saveLlmConfig());
    // Trigger buttons — delegated from container
    const container = byId('agents-container');
    if (container) {
      container.addEventListener('click', (e) => {
        const btn = e.target.closest('.agent-trigger-btn');
        if (btn && btn.dataset.agent) this.triggerAgent(btn.dataset.agent);
      });
    }
    // Prompt tab switching
    document.querySelectorAll('.prompt-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => this.showPrompt(btn.dataset.prompt));
    });
  },

  async refresh() {
    const el = byId('agents-container');
    if (el) el.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:20px">Loading agent status...</p>';
    await Promise.all([this.loadStatus(), this.loadPrompts(), this.loadLlmConfig()]);
  },

  async loadStatus() {
    try {
      const data = await API.quantStatus();
      const el = byId('agents-container');
      if (!el) return;
      const agents = data.agents || [];
      if (!agents.length) {
        el.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:20px">No agents configured</p>';
        return;
      }
      el.innerHTML = agents.map(a => {
        const lastReport = a.last_report ? new Date(a.last_report * 1000).toLocaleString() : 'Never';
        const lastFile = a.last_report_file || '';
        const schedule = a.schedule || 'Manual';
        const color = a.color || 'var(--neon-blue)';
        return '<div class="glass-panel" style="padding:14px;margin-bottom:10px">' +
          '<div style="display:flex;justify-content:space-between;align-items:flex-start">' +
            '<div style="flex:1">' +
              '<div style="font-weight:700;font-size:14px;color:' + color + ';margin-bottom:4px">' +
                (a.emoji || '🤖') + ' ' + (a.name || a.id || 'Unknown') +
              '</div>' +
              '<div style="font-size:11px;color:var(--text-secondary);margin-bottom:2px">' +
                '<b>Role:</b> ' + (a.role || 'Unknown') +
              '</div>' +
              '<div style="font-size:11px;color:var(--text-secondary);margin-bottom:2px">' +
                '<b>Description:</b> ' + (a.description || a.desc || 'No description') +
              '</div>' +
              '<div style="font-size:10px;color:var(--text-secondary);margin-top:6px">' +
                '<div>⏰ Schedule: ' + schedule + '</div>' +
                '<div>📄 Last report: ' + lastReport + (lastFile ? ' (' + lastFile + ')' : '') + '</div>' +
              '</div>' +
            '</div>' +
            '<button class="btn btn-sm agent-trigger-btn" data-agent="' + (a.id || '') + '" style="margin-left:12px;white-space:nowrap">⚡ Run Now</button>' +
          '</div>' +
        '</div>';
      }).join('');
    } catch (e) { /* silent */ }
  },

  async loadPrompts() {
    try {
      const data = await API.prompts();
      if (!data) return;
      // Store for prompt tabs
      this._prompts = data;
      // Show the first prompt's name in the selector
      const promptKeys = Object.keys(data).filter(k => k.startsWith('prompt_'));
      const container = byId('prompts-tab-container');
      if (!container || !promptKeys.length) return;

      // Show first prompt by default
      const firstKey = promptKeys[0];
      this.showPrompt(firstKey);
    } catch (e) { /* silent */ }
  },

  showPrompt(key) {
    if (!this._prompts || !this._prompts[key]) return;
    const container = byId('prompts-tab-container');
    if (!container) return;

    const promptKeys = Object.keys(this._prompts).filter(k => k.startsWith('prompt_'));
    const friendlyNames = {
      prompt_quant: '📊 Quant Optimizer',
      prompt_dev: '💻 Developer/Architect',
      prompt_blog: '📝 Blog Writer',
      prompt_nn: '🧠 Neural Network',
      prompt_sentiment: '📈 Sentiment Analyst',
      prompt_risk: '🛡️ Risk Auditor',
      prompt_allocator: '⚖️ Allocator',
      prompt_self_developer: '🔧 Self-Developer',
      prompt_self_improvement: '🔄 Self-Improvement',
    };

    container.innerHTML =
      '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">' +
        promptKeys.map(k =>
          '<button class="btn btn-sm prompt-tab-btn' + (k === key ? ' active' : '') + '" data-prompt="' + k + '" style="font-size:11px">' +
            (friendlyNames[k] || k.replace('prompt_', '')) +
          '</button>'
        ).join('') +
      '</div>' +
      '<div style="margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">' +
        '<span style="font-weight:700;color:var(--neon-blue)">' + (friendlyNames[key] || key) + '</span>' +
        '<span style="font-size:10px;color:var(--text-secondary)">' + this._prompts[key].length.toLocaleString() + ' chars</span>' +
      '</div>' +
      '<textarea id="prompts-editor" style="width:100%;min-height:300px;font-family:var(--font-mono);font-size:11px;line-height:1.6;padding:12px;background:rgba(0,0,0,0.2);border:1px solid var(--border-color);border-radius:8px;color:var(--text-primary);resize:vertical">' +
        this._prompts[key].replace(/</g, '&lt;') +
      '</textarea>' +
      '<input type="hidden" id="prompts-active-key" value="' + key + '">';

    // Re-bind tab buttons
    container.querySelectorAll('.prompt-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => this.showPrompt(btn.dataset.prompt));
    });
  },

  async loadLlmConfig() {
    try {
      const data = await API.agentLlm();
      if (!data) return;
      setInput('agent-llm-provider', data.provider);
      setInput('agent-llm-model', data.model);
      setInput('agent-llm-url', data.base_url);
      setCheckbox('agent-llm-enabled', data.enabled);
    } catch (e) { /* silent */ }
  },

  async triggerAgent(agent) {
    if (!agent) return;
    App.toast('Triggering ' + agent + '...', 'info');
    try {
      await API.triggerQuant(agent);
      App.toast(agent + ' triggered', 'success');
      this.loadStatus();
    } catch (e) { App.toast('Trigger failed: ' + e.message, 'error'); }
  },

  async triggerAll() {
    App.toast('Triggering all agents...', 'info');
    try {
      await API.applyAllOptimizations();
      App.toast('All agents triggered', 'success');
      this.loadStatus();
    } catch (e) { App.toast('Trigger all failed: ' + e.message, 'error'); }
  },

  async savePrompts() {
    try {
      const key = byId('prompts-active-key')?.value;
      const text = byId('prompts-editor')?.value;
      if (!key || !text) { App.toast('No prompt to save', 'error'); return; }
      await API.savePrompt({ key: key, prompt: text });
      // Update cache
      if (this._prompts) this._prompts[key] = text;
      App.toast('Prompt "' + key + '" saved', 'success');
    } catch (e) { App.toast('Save failed: ' + e.message, 'error'); }
  },

  async saveLlmConfig() {
    try {
      const data = {
        enabled: byId('agent-llm-enabled')?.checked ?? true,
        provider: byId('agent-llm-provider')?.value || 'anthropic',
        model: byId('agent-llm-model')?.value || '',
        server_url: byId('agent-llm-url')?.value || '',
      };
      await API.setAgentLlm(data);
      App.toast('LLM config saved', 'success');
    } catch (e) { App.toast('Save failed: ' + e.message, 'error'); }
  },
};
document.addEventListener('DOMContentLoaded', () => { Agents.init(); if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 200); });
