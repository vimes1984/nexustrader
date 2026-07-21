/**
 * agents.js v3 — Quant Team agents tab
 */
const Agents = {
  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'agents') this.refresh(); });
    byId('btn-trigger-all')?.addEventListener('click', () => this.triggerAll());
    byId('btn-refresh-agents')?.addEventListener('click', () => this.refresh());
    byId('btn-save-prompts')?.addEventListener('click', () => this.savePrompts());
    byId('btn-save-agent-llm')?.addEventListener('click', () => this.saveLlmConfig());
    // Delegated trigger buttons
    byId('agents-container')?.addEventListener('click', (e) => {
      const btn = e.target.closest('.agent-trigger-btn');
      if (btn?.dataset.agent) this.triggerAgent(btn.dataset.agent);
    });
  },

  async refresh() {
    const el = byId('agents-container');
    if (el) el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px">Loading agents...</p>';
    await Promise.all([this.loadStatus(), this.loadPrompts(), this.loadLlmConfig()]);
  },

  async loadStatus() {
    try {
      const data = await API.quantStatus();
      const el = byId('agents-container'); if (!el) return;
      const agents = data?.agents || [];
      if (!agents.length) {
        el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px">No agents configured</p>';
        return;
      }
      el.innerHTML = agents.map(a => {
        const lastReport = a.last_report ? new Date(Number(a.last_report) * 1000).toLocaleString() : 'Never';
        const color = a.color || 'var(--neon-blue)';
        return `<div class="glass-panel" style="padding:14px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div style="flex:1">
              <div style="font-weight:700;font-size:14px;color:${color};margin-bottom:4px">${a.emoji||'🤖'} ${a.name||a.id||'Unknown'}</div>
              <div style="font-size:11px;color:var(--text-secondary);margin-bottom:2px"><b>Role:</b> ${a.role||'—'}</div>
              <div style="font-size:11px;color:var(--text-secondary);margin-bottom:2px">${a.description||a.desc||''}</div>
              <div style="font-size:10px;color:var(--text-muted);margin-top:6px">⏰ ${a.schedule||'Manual'} · 📄 ${lastReport}${a.last_report_file?' ('+a.last_report_file+')':''}</div>
            </div>
            <button class="btn btn-sm agent-trigger-btn" data-agent="${a.id||''}" style="margin-left:12px;flex-shrink:0">⚡ Run</button>
          </div>
        </div>`;
      }).join('');
    } catch(e) { /* silent */ }
  },

  async loadPrompts() {
    try {
      const data = await API.prompts();
      if (!data) return;
      this._prompts = data;
      const keys = Object.keys(data).filter(k => k.startsWith('prompt_'));
      if (keys.length) this.showPrompt(keys[0]);
    } catch(e) {}
  },

  showPrompt(key) {
    if (!this._prompts?.[key]) return;
    const container = byId('prompts-tab-container'); if (!container) return;

    const names = {
      prompt_quant: '📊 Quant Optimizer', prompt_dev: '💻 Developer', prompt_blog: '📝 Blog Writer',
      prompt_nn: '🧠 Neural Network', prompt_sentiment: '📈 Sentiment', prompt_risk: '🛡️ Risk Auditor',
      prompt_allocator: '⚖️ Allocator', prompt_self_developer: '🔧 Self-Developer', prompt_self_improvement: '🔄 Self-Improvement',
    };

    const keys = Object.keys(this._prompts).filter(k => k.startsWith('prompt_'));
    container.innerHTML =
      '<div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap">' +
        keys.map(k => `<button class="btn btn-sm prompt-tab-btn${k===key?' active':''}" data-prompt="${k}" style="font-size:10px;${k===key?'background:rgba(59,130,246,0.15);border-color:rgba(59,130,246,0.3);color:var(--neon-blue)':''}">${names[k]||k.replace('prompt_','')}</button>`).join('') +
      '</div>' +
      '<div style="margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">' +
        '<span style="font-weight:700;font-size:13px;color:var(--neon-blue)">'+(names[key]||key)+'</span>' +
        '<span style="font-size:10px;color:var(--text-muted)">'+this._prompts[key].length.toLocaleString()+' chars</span>' +
      '</div>' +
      '<textarea id="prompts-editor" style="width:100%;min-height:300px;font-size:11px;line-height:1.7;padding:12px;background:rgba(0,0,0,0.2);border:1px solid var(--border-color);border-radius:8px;color:var(--text-primary);resize:vertical;font-family:var(--font-mono)">' +
        this._prompts[key].replace(/</g,'&lt;') +
      '</textarea>' +
      '<input type="hidden" id="prompts-active-key" value="'+key+'">';

    container.querySelectorAll('.prompt-tab-btn').forEach(b => {
      b.addEventListener('click', () => this.showPrompt(b.dataset.prompt));
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
    } catch(e) {}
  },

  async triggerAgent(agent) {
    if (!agent) return;
    App.toast('Triggering ' + agent + '...', 'info');
    try { await API.triggerQuant(agent); App.toast(agent + ' triggered', 'success'); this.loadStatus(); }
    catch(e) { App.toast('Trigger failed: ' + e.message, 'error'); }
  },

  async triggerAll() {
    App.toast('Triggering all agents...', 'info');
    try {
      await API.triggerSelfDev();
      await API.triggerNnOptimize();
      await API.triggerSentiment();
      await API.triggerRiskAudit();
      await API.triggerAllocator();
      App.toast('All agents triggered', 'success');
      this.loadStatus();
    } catch(e) { App.toast('Trigger all failed: ' + e.message, 'error'); }
  },

  async savePrompts() {
    try {
      const key = byId('prompts-active-key')?.value;
      const text = byId('prompts-editor')?.value;
      if (!key || !text) { App.toast('No prompt selected', 'error'); return; }
      await API.savePrompt({ key, prompt: text });
      if (this._prompts) this._prompts[key] = text;
      App.toast('Prompt saved: ' + key, 'success');
    } catch(e) { App.toast('Save failed: ' + e.message, 'error'); }
  },

  async saveLlmConfig() {
    try {
      await API.setAgentLlm({
        provider: getInput('agent-llm-provider') || 'anthropic',
        model: getInput('agent-llm-model') || '',
        base_url: getInput('agent-llm-url') || '',
        enabled: byId('agent-llm-enabled')?.checked ?? true,
      });
      App.toast('Agent LLM config saved', 'success');
    } catch(e) { App.toast('Save failed: ' + e.message, 'error'); }
  },
};

document.addEventListener('DOMContentLoaded', () => { Agents.init(); lucide?.createIcons(); });
