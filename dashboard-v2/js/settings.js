/**
 * settings.js — Trading System + Notifications + Optimizations tabs
 */

function setInput(id, val) {
  const el = byId(id);
  if (el) el.value = val ?? '';
}
function setCheckbox(id, val) {
  const el = byId(id);
  if (el) el.checked = !!val;
}

const Settings = {
  init() {
    document.addEventListener('nt:tabChange', (e) => {
      if (e.detail === 'settings') this.refresh();
      if (e.detail === 'notifications') this.refreshNotifications();
      if (e.detail === 'optimizations') this.refreshOpts();
    });
    // Risk / System
    byId('btn-test-broker')?.addEventListener('click', () => this.testBroker());
    byId('btn-reset-cooldowns')?.addEventListener('click', () => this.resetCooldowns());
    byId('btn-save-config')?.addEventListener('click', () => this.saveConfig());
    byId('btn-set-daily-goal')?.addEventListener('click', () => this.setDailyGoal());
    byId('btn-backtest')?.addEventListener('click', () => this.runBacktest());
    byId('btn-create-backup')?.addEventListener('click', () => this.createBackup());
    // Notifications
    byId('btn-save-notif')?.addEventListener('click', () => this.saveNotifications());
    byId('btn-test-notif')?.addEventListener('click', () => this.testNotification());
    // Optimizations
    byId('btn-apply-all-opts')?.addEventListener('click', () => this.applyAll());
    byId('btn-review-opts')?.addEventListener('click', () => this.review());
    byId('btn-opt-params')?.addEventListener('click', () => this.optimizeParams());
    byId('btn-opt-longterm')?.addEventListener('click', () => this.optimizeLongTerm());
  },

  async refresh() {
    await Promise.all([this.loadConfig(), this.loadDailyGoal()]);
  },

  async loadConfig() {
    try {
      const data = await API.systemConfig();
      // Map API response to HTML fields
      setInput('config-max-position', data.max_position_size);
      setInput('config-max-drawdown', data.max_drawdown);
      setInput('config-cooldown', data.cooldown);
      setInput('config-tp', data.tp_multiplier);
      setInput('config-sl', data.sl_multiplier);
      setInput('config-nn-lr', data.nn_lr);
      setInput('config-nn-dim', data.nn_hidden_dim);
      setInput('config-nn-layers', data.nn_hidden_layers);
      if (typeof data.trailing_stop === 'boolean') setCheckbox('config-trailing-stop', data.trailing_stop);
      // Broker info (read-only display)
      const brokerEl = byId('config-broker-info');
      if (brokerEl) brokerEl.textContent = `Broker: ${data.broker || 'kraken'} | Key: ${(data.api_key || '').slice(0,12)}... | Mode: ${data.trading_mode}`;
    } catch (e) { /* silent */ }
  },

  async loadDailyGoal() {
    try {
      const data = await API.dailyGoal();
      setInput('daily-goal-amount', data.goal);
      setCheckbox('daily-goal-enabled', data.enabled);
      const el = byId('daily-goal-status');
      if (el) el.textContent = `Progress: $${data.today_pnl || 0} / $${data.goal || 1000} (${data.progress_pct || 0}%)`;
    } catch (e) { /* silent */ }
  },

  async saveConfig() {
    try {
      const data = {
        max_position_size: parseFloat(byId('config-max-position')?.value) || 0,
        max_drawdown: parseFloat(byId('config-max-drawdown')?.value) || 0,
        cooldown_minutes: parseInt(byId('config-cooldown')?.value) || 0,
      };
      await API.setSystemConfig(data);
      App.toast('Config saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },

  async testBroker() {
    App.toast('Testing broker connection...', 'info');
    try {
      const data = await API.testBroker();
      App.toast(data.ok ? 'Broker connected' : 'Broker connection failed', data.ok ? 'success' : 'error');
    } catch (e) {
      App.toast('Test failed: ' + e.message, 'error');
    }
  },

  async resetCooldowns() {
    try {
      await API.resetCooldowns();
      App.toast('Cooldowns reset', 'success');
    } catch (e) {
      App.toast('Reset failed: ' + e.message, 'error');
    }
  },

  async setDailyGoal() {
    try {
      const data = {
        amount: parseFloat(byId('daily-goal-amount')?.value) || 0,
        enabled: byId('daily-goal-enabled')?.checked ?? false,
      };
      await API.setDailyGoal(data);
      App.toast('Daily goal updated', 'success');
    } catch (e) {
      App.toast('Goal update failed: ' + e.message, 'error');
    }
  },

  async runBacktest() {
    const ticker = App.state.activeTicker;
    const days = parseInt(prompt('Days to backtest?', '30')) || 30;
    App.toast(`Running ${days}d backtest for ${ticker}...`, 'info');
    try {
      const data = await API.backtest({ ticker, days });
      const el = byId('backtest-results');
      if (el) el.innerHTML = `<pre style="font-size:11px;white-space:pre-wrap">${JSON.stringify(data, null, 2)}</pre>`;
      App.toast('Backtest complete', 'success');
    } catch (e) {
      App.toast('Backtest failed: ' + e.message, 'error');
    }
  },

  async createBackup() {
    App.toast('Creating backup...', 'info');
    try {
      const data = await API.createBackup();
      App.toast(`Backup created: ${data.filename || 'success'}`, 'success');
    } catch (e) {
      App.toast('Backup failed: ' + e.message, 'error');
    }
  },

  // ── Notifications ──
  async refreshNotifications() {
    try {
      const data = await API.notifications();
      // API returns flat keys: smtp_host, smtp_port, smtp_user, email_enabled, email_recipient
      setInput('notif-smtp-host', data.smtp_host);
      setInput('notif-smtp-port', data.smtp_port);
      setInput('notif-smtp-user', data.smtp_user);
      setInput('notif-smtp-pass', data.smtp_pass);
      setCheckbox('notif-email-enabled', data.email_enabled);
      setInput('notif-email-recipient', data.email_recipient);
    } catch (e) { /* silent */ }
  },

  async saveNotifications() {
    try {
      const data = {
        smtp_host: byId('notif-smtp-host')?.value,
        smtp_port: parseInt(byId('notif-smtp-port')?.value) || 587,
        smtp_user: byId('notif-smtp-user')?.value,
        smtp_pass: byId('notif-smtp-pass')?.value,
        email_enabled: byId('notif-email-enabled')?.checked ?? false,
        email_recipient: byId('notif-email-recipient')?.value,
      };
      await API.setNotifications(data);
      App.toast('Notification settings saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },

  async testNotification() {
    App.toast('Sending test notification...', 'info');
    try {
      await API.testNotification();
      App.toast('Test notification sent', 'success');
    } catch (e) {
      App.toast('Test failed: ' + e.message, 'error');
    }
  },

  // ── Optimizations ──
  async refreshOpts() {
    try {
      const data = await API.optimizations();
      const container = byId('optimizations-list');
      if (!container) return;
      if (!data.suggestions || data.suggestions.length === 0) {
        container.innerHTML = '<p style="color:var(--text-secondary)">No optimization suggestions</p>';
        return;
      }
      container.innerHTML = data.suggestions.map((o, i) => `
        <div class="glass-panel" style="padding:10px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
          <div style="font-size:12px">
            <b>${o.id || o.name || `Suggestion #${i+1}`}</b>
            <span style="color:var(--text-secondary)">${o.description || ''}</span>
          </div>
          <button class="btn btn-sm" onclick="Settings.applyOne('${o.id || o.name}')">Apply</button>
        </div>
      `).join('');
    } catch (e) { /* silent */ }
  },

  async applyOne(id) {
    try {
      await API.applyOptimization(id);
      App.toast(`Applied: ${id}`, 'success');
    } catch (e) {
      App.toast('Apply failed: ' + e.message, 'error');
    }
  },

  async applyAll() {
    App.toast('Applying all optimizations...', 'info');
    try {
      await API.applyAllOptimizations();
      App.toast('All optimizations applied', 'success');
    } catch (e) {
      App.toast('Apply failed: ' + e.message, 'error');
    }
  },

  async review() {
    App.toast('Reviewing optimizations...', 'info');
    try {
      const data = await API.reviewOptimization();
      App.toast('Review complete', 'success');
      this.refreshOpts();
    } catch (e) {
      App.toast('Review failed: ' + e.message, 'error');
    }
  },

  async optimizeParams() {
    App.toast('Optimizing parameters...', 'info');
    try {
      await API.optimizeParameters();
      App.toast('Parameters optimized', 'success');
    } catch (e) {
      App.toast('Optimization failed: ' + e.message, 'error');
    }
  },

  async optimizeLongTerm() {
    App.toast('Running long-term optimization...', 'info');
    try {
      await API.optimizeLongTerm();
      App.toast('Long-term optimization complete', 'success');
    } catch (e) {
      App.toast('Optimization failed: ' + e.message, 'error');
    }
  },
};
document.addEventListener('DOMContentLoaded', () => Settings.init());
