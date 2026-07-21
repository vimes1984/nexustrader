/**
 * agents.js — AI Agent Nexus tab: Quant Team status, triggers, prompts
 */
const Agents = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'agents') this.refresh();
    });
    byId('btn-trigger-quant')?.addEventListener('click', () => this.triggerAgent());
    byId('btn-trigger-all')?.addEventListener('click', () => this.triggerAll());
    byId('btn-save-prompt')?.addEventListener('click', () => this.savePrompt());
    byId('btn-trigger-self-dev')?.addEventListener('click', () => this.trigger('self_dev'));
    byId('btn-trigger-nn')?.addEventListener('click', () => this.trigger('nn'));
    byId('btn-trigger-sentiment')?.addEventListener('click', () => this.trigger('sentiment'));
    byId('btn-trigger-risk')?.addEventListener('click', () => this.trigger('risk_audit'));
    byId('btn-trigger-alloc')?.addEventListener('click', () => this.trigger('allocator'));
  },

  async refresh() {
    await Promise.all([this.loadStatus(), this.loadPrompts(), this.loadLlmConfig()]);
  },

  async loadStatus() {
    try {
      const data = await API.quantStatus();
      const container = byId('agents-status');
      if (!container) return;

      const agents = data.agents || data;
      const agentList = Array.isArray(agents) ? agents : Object.entries(agents).map(([k, v]) => ({ name: k, ...v }));

      container.innerHTML = agentList.map(a => `
        <div class="glass-panel" style="padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">
          <div>
            <b>${a.name || a.id || 'Unknown'}</b>
            <span style="color:${a.status === 'running' ? 'var(--neon-green)' : 'var(--text-secondary)'};margin-left:8px;font-size:10px">
              ${a.status || 'idle'}
            </span>
            ${a.last_run ? `<span style="color:var(--text-secondary);font-size:10px;margin-left:8px">Last: ${a.last_run}</span>` : ''}
          </div>
          <button class="btn btn-sm" onclick="Agents.triggerAgent('${a.name || a.id}')">Run</button>
        </div>
      `).join('');

      if (agentList.length === 0) {
        container.innerHTML = '<p style="color:var(--text-secondary)">No quant agents configured</p>';
      }
    } catch (e) {
      App.toast('Failed to load agent status: ' + e.message, 'error');
    }
  },

  async loadPrompts() {
    try {
      const data = await API.prompts();
      const el = byId('prompts-editor');
      if (!el || !data) return;
      if (data.prompts) {
        el.value = JSON.stringify(data.prompts, null, 2);
      }
    } catch (e) { /* silent */ }
  },

  async loadLlmConfig() {
    try {
      const data = await API.agentLlm();
      byId('agent-llm-enabled')?.checked = data.enabled || false;
      byId('agent-llm-model')?.value = data.model || '';
    } catch (e) { /* silent */ }
  },

  async triggerAgent(agent) {
    agent = agent || prompt('Agent name:');
    if (!agent) return;
    App.toast(`Triggering ${agent}...`, 'info');
    try {
      await API.triggerQuant(agent);
      App.toast(`${agent} triggered`, 'success');
      this.loadStatus();
    } catch (e) {
      App.toast('Trigger failed: ' + e.message, 'error');
    }
  },

  async triggerAll() {
    App.toast('Triggering all agents...', 'info');
    const promises = [
      API.triggerSelfDev(),
      API.triggerNnOptimize(),
      API.triggerSentiment(),
      API.triggerRiskAudit(),
      API.triggerAllocator(),
    ];
    try {
      await Promise.allSettled(promises);
      App.toast('All agents triggered', 'success');
      this.loadStatus();
    } catch (e) {
      App.toast('Some triggers failed', 'error');
    }
  },

  async trigger(type) {
    const map = {
      self_dev: API.triggerSelfDev,
      nn: API.triggerNnOptimize,
      sentiment: API.triggerSentiment,
      risk_audit: API.triggerRiskAudit,
      allocator: API.triggerAllocator,
    };
    const fn = map[type];
    if (!fn) return;
    App.toast(`Triggering ${type}...`, 'info');
    try {
      await fn.call(API);
      App.toast(`${type} complete`, 'success');
    } catch (e) {
      App.toast(`${type} failed: ` + e.message, 'error');
    }
  },

  async savePrompt() {
    const raw = byId('prompts-editor')?.value;
    if (!raw) return;
    try {
      const data = JSON.parse(raw);
      await API.savePrompt(data);
      App.toast('Prompts saved', 'success');
    } catch (e) {
      App.toast('Invalid JSON or save failed: ' + e.message, 'error');
    }
  },
};
document.addEventListener('DOMContentLoaded', () => Agents.init());
