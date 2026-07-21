/**
 * optimizations.js v3 — Optimization suggestions tab
 */
const Optimizations = {
  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'optimizations') this.load(); });
    byId('btn-apply-all-opts')?.addEventListener('click', () => this.applyAll());
    byId('btn-review-opts')?.addEventListener('click', () => this.review());
    byId('btn-opt-params')?.addEventListener('click', () => this.optimizeParams());
    byId('btn-opt-longterm')?.addEventListener('click', () => this.longTerm());
    byId('btn-flush-opts')?.addEventListener('click', () => this.flush());
    // Delegated apply-per-item
    byId('optimizations-list')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-opt-id]');
      if (btn) this.applyOne(btn.dataset.optId);
    });
  },

  async load() {
    const el = byId('optimizations-list'); if (!el) return;
    el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px">Loading optimization data...</p>';
    try {
      const data = await API.optimizations();
      const opts = data?.optimizations || [];
      if (!opts.length) {
        el.innerHTML = '<div class="empty-state"><div class="empty-state-icon" style="font-size:36px">🧹</div><div class="empty-state-title">All optimized</div><div class="empty-state-desc">No pending optimizations. Agents haven\'t suggested any changes yet.</div></div>';
        return;
      }
      el.innerHTML = opts.map(o => {
        const ts = o.timestamp ? new Date(Number(o.timestamp) * 1000).toLocaleString() : '—';
        const icons = { quant: '📊', risk: '🛡️', nn: '🧠', allocator: '⚖️', sentiment: '📈', self_dev: '🔧', self_improve: '🔄' };
        const icon = icons[o.agent] || '🤖';
        return `<div class="glass-panel" style="padding:12px 14px;margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div style="flex:1">
              <div style="font-weight:600;font-size:12px;margin-bottom:4px">${icon} ${o.agent || 'system'} → ${o.parameter || '?'}</div>
              <div style="font-size:10px;color:var(--text-muted)">
                <span style="background:rgba(244,63,94,0.1);padding:1px 6px;border-radius:3px;color:var(--neon-red);font-family:var(--font-mono)">${o.old_value || '—'}</span>
                → <span style="background:rgba(16,185,129,0.1);padding:1px 6px;border-radius:3px;color:var(--neon-green);font-family:var(--font-mono)">${o.new_value || '—'}</span>
              </div>
              ${o.rationale ? `<div style="font-size:10px;color:var(--text-secondary);margin-top:4px;line-height:1.4">${o.rationale.substring(0,120)}${o.rationale.length>120?'...':''}</div>` : ''}
              <div style="font-size:9px;color:var(--text-muted);margin-top:4px">⏰ ${ts}</div>
            </div>
            <button class="btn btn-sm btn-primary" data-opt-id="${o.id || ''}" style="margin-left:10px;flex-shrink:0">Apply</button>
          </div>
        </div>`;
      }).join('');
    } catch(e) {
      el.innerHTML = '<div class="empty-state"><div class="empty-state-icon" style="font-size:36px">❌</div><div class="empty-state-title">Failed to load</div><div class="empty-state-desc">Could not fetch optimization data from the server.</div></div>';
    }
  },

  async applyOne(id) {
    App.toast('Applying optimization #'+id+'...', 'info');
    try {
      await API.applyOptimization(id);
      App.toast('Optimization applied ✅', 'success');
      this.load();
    } catch(e) { App.toast('Apply failed: ' + e.message, 'error'); }
  },

  async applyAll() {
    if (!confirm('Apply ALL pending optimizations?')) return;
    App.toast('Applying all optimizations...', 'info');
    try {
      const data = await API.applyAllOptimizations();
      App.toast(data.ok ? 'All applied!' : 'Some failed', data.ok ? 'success' : 'warn');
      this.load();
    } catch(e) { App.toast('Apply all failed: ' + e.message, 'error'); }
  },

  async review() {
    App.toast('Requesting agent review...', 'info');
    try {
      await API.reviewOptimizations();
      App.toast('Review requests sent', 'success');
    } catch(e) { App.toast('Review failed: ' + e.message, 'error'); }
  },

  async optimizeParams() {
    App.toast('Triggering parameter optimization...', 'info');
    try {
      await API.triggerOptimization();
      App.toast('Optimization triggered', 'success');
    } catch(e) { App.toast('Trigger failed: ' + e.message, 'error'); }
  },

  async longTerm() {
    if (!confirm('Run long-term optimization? This may take a while.')) return;
    App.toast('Starting long-term optimize...', 'info');
    try {
      await API.longTermOptimize();
      App.toast('Long-term optimize started', 'success');
    } catch(e) { App.toast('Long-term failed: ' + e.message, 'error'); }
  },

  async flush() {
    if (!confirm('Delete ALL pending optimizations?')) return;
    try {
      await API.flushOptimizations();
      App.toast('Optimizations flushed', 'success');
      this.load();
    } catch(e) { App.toast('Flush failed: ' + e.message, 'error'); }
  },
};

document.addEventListener('DOMContentLoaded', () => { Optimizations.init(); lucide?.createIcons(); });
