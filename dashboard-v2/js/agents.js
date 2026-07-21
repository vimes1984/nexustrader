/**
 * agents.js — AI Agents tab: Quant Team status, prompts, LLM config, triggers
 */

function setInput(id, val) { const el = byId(id); if (el) el.value = val ?? ''; }
function setCheckbox(id, val) { const el = byId(id); if (el) el.checked = !!val; }

const Agents = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'agents') this.refresh();
    });
    // Trigger buttons
    document.querySelectorAll('.btn-trigger-agent').forEach(btn => {
      btn.addEventListener('click', () => this.triggerAgent(btn.dataset.agent));
    });
    byId('btn-trigger-all')?.addEventListener('click', () => this.triggerAll());
    byId('btn-save-prompts')?.addEventListener('click', () => this.savePrompts());
    byId('btn-save-agent-llm')?.addEventListener('click', () => this.saveLlmConfig());
  },

  async refresh() {
    await Promise.all([this.loadStatus(), this.loadPrompts(), this.loadLlmConfig()]);
  },

  // ACTUAL API: {agents: [{id, name, emoji, role, description, last_run, status}]}
  async loadStatus() {
    try {
      const data = await API.quantStatus();
      const container = byId('agents-list');
      if (!container || !data.agents) return;
      container.innerHTML = data.agents.map(a =>
        '<div class="glass-panel" style="padding:12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">' +
          '<div style="display:flex;align-items:center;gap:8px">' +
            '<span style="font-size:20px">' + (a.emoji || '🤖') + '</span>' +
            '<div>' +
              '<b>' + (a.name || a.id) + '</b>' +
              '<div style="font-size:10px;color:var(--text-secondary)">' + (a.role || a.description || '') + '</div>' +
              '<div style="font-size:10px;color:var(--text-secondary)">Last run: ' + (a.last_run || 'never') + '</div>' +
            '</div>' +
          '</div>' +
          '<div style="display:flex;gap:6px">' +
            '<span style="font-size:11px;color:' + (a.status === 'running' ? 'var(--neon-green)' : 'var(--text-secondary)') + '">' + (a.status || 'idle') + '</span>' +
            '<button class="btn btn-sm" onclick="Agents.triggerAgent(\'' + (a.id || '') + '\')">Run</button>' +
          '</div>' +
        '</div>'
      ).join('');
    } catch (e) { /* silent */ }
  },

  // ACTUAL API: {prompt_quant, prompt_dev, prompt_blog, prompt_nn, prompt_sentiment,
  //               prompt_risk, prompt_allocator, prompt_self_developer, prompt_self_improvement, ...}
  async loadPrompts() {
    try {
      const data = await API.prompts();
      const el = byId('prompts-editor');
      if (!el || !data) return;
      // Show only prompt_* keys
      const prompts = {};
      for (const [k, v] of Object.entries(data)) {
        if (k.startsWith('prompt_')) prompts[k] = v;
      }
      el.value = JSON.stringify(prompts, null, 2);
    } catch (e) { /* silent */ }
  },

  // ACTUAL API: {provider, base_url, model, api_key}
  async loadLlmConfig() {
    try {
      const data = await API.agentLlm();
      if (!data) return;
      setInput('agent-llm-provider', data.provider);
      setInput('agent-llm-model', data.model);
      setInput('agent-llm-url', data.base_url);
    } catch (e) { /* silent */ }
  },

  async triggerAgent(agent) {
    agent = agent || prompt('Agent ID (e.g. quant-optimizer):');
    if (!agent) return;
    App.toast('Triggering ' + agent + '...', 'info');
    try {
      await API.triggerQuant(agent);
      App.toast(agent + ' triggered', 'success');
      this.loadStatus();
    } catch (e) {
      App.toast('Trigger failed: ' + e.message, 'error');
    }
  },

  async triggerAll() {
    App.toast('Triggering all agents...', 'info');
    try {
      await Promise.all([
        API.triggerSelfDev(),
        API.triggerNnOptimize(),
        API.triggerSentiment(),
        API.triggerRiskAudit(),
        API.triggerAllocator(),
      ]);
      App.toast('All agents triggered', 'success');
      this.loadStatus();
    } catch (e) {
      App.toast('Trigger all failed: ' + e.message, 'error');
    }
  },

  async savePrompts() {
    try {
      const text = byId('prompts-editor')?.value;
      if (!text) { App.toast('No prompts to save', 'error'); return; }
      const prompts = JSON.parse(text);
      // Save each prompt as a separate key
      for (const [k, v] of Object.entries(prompts)) {
        await API.savePrompt({ key: k, prompt: v });
      }
      App.toast('Prompts saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },

  async saveLlmConfig() {
    try {
      const data = {
        enabled: true,
        provider: byId('agent-llm-provider')?.value || 'anthropic',
        model: byId('agent-llm-model')?.value || '',
        server_url: byId('agent-llm-url')?.value || '',
      };
      await API.setAgentLlm(data);
      App.toast('LLM config saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },
};
document.addEventListener('DOMContentLoaded', () => Agents.init());
