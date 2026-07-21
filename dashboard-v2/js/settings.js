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
    byId('btn-test-broker')?.addEventListener('click', () => this.testBroker());
    byId('btn-save-broker')?.addEventListener('click', () => this.saveBrokerConfig());
    byId('btn-reset-cooldowns')?.addEventListener('click', () => this.resetCooldowns());
    byId('btn-save-config')?.addEventListener('click', () => this.saveConfig());
    byId('btn-set-daily-goal')?.addEventListener('click', () => this.setDailyGoal());
    byId('btn-backtest')?.addEventListener('click', () => this.runBacktest());
    byId('btn-create-backup')?.addEventListener('click', () => this.createBackup());
    byId('btn-save-notif')?.addEventListener('click', () => this.saveNotifications());
    byId('btn-test-notif')?.addEventListener('click', () => this.testNotification());
    byId('btn-apply-all-opts')?.addEventListener('click', () => this.applyAll());
    byId('btn-review-opts')?.addEventListener('click', () => this.review());
    byId('btn-opt-params')?.addEventListener('click', () => this.optimizeParams());
    byId('btn-opt-longterm')?.addEventListener('click', () => this.optimizeLongTerm());
  },

  async refresh() {
    await Promise.all([this.loadConfig(), this.loadDailyGoal(), this.loadBrokerConfig()]);
  },

  // ACTUAL API: {trading_mode, broker, api_key, api_secret, trailing_stop, cooldown,
  //               tp_multiplier, sl_multiplier, risk_mode, max_drawdown,
  //               nn_lr, nn_floor, nn_discount, nn_exploration, nn_hidden_layers,
  //               nn_hidden_dim, nn_dropout, nn_optimizer, nn_epochs, initial_balance}
  // ACTUAL API: {trading_mode, broker, api_key, api_secret, trailing_stop, cooldown,
  //               tp_multiplier, sl_multiplier, risk_mode, max_drawdown,
  //               nn_lr, nn_floor, nn_discount, nn_exploration, initial_balance,
  //               nn_hidden_layers, nn_hidden_dim, nn_dropout, nn_optimizer, nn_epochs}
  async loadConfig() {
    try {
      const data = await API.systemConfig();
      if (!data) return;
      setInput('config-max-position', data.initial_balance || '');
      setInput('config-max-drawdown', data.max_drawdown || '');
      setInput('config-cooldown', data.cooldown || '');
      setInput('config-tp', data.tp_multiplier || '');
      setInput('config-sl', data.sl_multiplier || '');
      setInput('config-nn-lr', data.nn_lr || '');
      setInput('config-nn-dim', data.nn_hidden_dim || '');
      setInput('config-nn-layers', data.nn_hidden_layers || '');
      setCheckbox('config-trailing-stop', data.trailing_stop);
    } catch (e) { /* silent */ }
  },

  // ACTUAL API: {status, daily_income_goal}
  async loadDailyGoal() {
    try {
      const data = await API.dailyGoal();
      if (!data) return;
      setInput('daily-goal-amount', data.daily_income_goal);
      setCheckbox('daily-goal-enabled', data.daily_income_goal > 0);
      const el = byId('daily-goal-status');
      if (el) el.textContent = data.daily_income_goal ? 'Daily goal: $' + data.daily_income_goal : 'No goal set';
    } catch (e) { /* silent */ }
  },


  // ACTUAL API: {broker, api_key, api_secret, trading_mode, test_result}
  async loadBrokerConfig() {
    try {
      const data = await API.brokerConfig();
      if (!data) return;
      setInput('config-broker-type', data.broker || 'kraken');
      setInput('config-broker-key', data.api_key || '');
      setInput('config-broker-secret', data.api_secret || '');
      const modeEl = byId('config-trading-mode');
      if (modeEl) modeEl.value = data.trading_mode || 'paper';
      const statusEl = byId('broker-status-display');
      if (statusEl && data.test_result) {
        statusEl.innerHTML = '<span class="broker-status-ok">Last test: ' + data.test_result + '</span>';
      }
    } catch (e) { /* silent */ }
  },

  async saveBrokerConfig() {
    try {
      const data = {
        broker: byId('config-broker-type')?.value || 'kraken',
        api_key: byId('config-broker-key')?.value || '',
        api_secret: byId('config-broker-secret')?.value || '',
        trading_mode: byId('config-trading-mode')?.value || 'paper',
      };
      await API.setBrokerConfig(data);
      App.toast('Broker config saved', 'success');
    } catch (e) { App.toast('Save failed: ' + e.message, 'error'); }
  },

  async saveConfig() {
    try {
      const payload = {
        max_position_size: parseFloat(byId('config-max-position')?.value) || 0,
        max_drawdown: parseFloat(byId('config-max-drawdown')?.value) || 0,
        cooldown_minutes: parseInt(byId('config-cooldown')?.value) || 0,
        tp_multiplier: parseFloat(byId('config-tp')?.value) || 0,
        sl_multiplier: parseFloat(byId('config-sl')?.value) || 0,
      };
      await API.setSystemConfig(payload);
      App.toast('Config saved', 'success');
    } catch (e) {
      App.toast('Save failed: ' + e.message, 'error');
    }
  },

  async testBroker() {
    App.toast('Testing broker connection...', 'info');
    try {
      const data = await API.testBroker();
      const success = data.ok || data.connected || data.status === 'success';
      App.toast(success ? 'Broker connected ✅ ' + (data.message || '') : 'Broker connection failed: ' + (data.error || 'unknown'), success ? 'success' : 'error');
      // Show balances in the status area
      if (data.balances) {
        const el = byId('backtest-results');
        if (el) el.innerHTML = '<pre style="font-size:11px;white-space:pre-wrap">Balances:\n' + JSON.stringify(data.balances, null, 2) + '</pre>';
      }
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
      const amount = parseFloat(byId('daily-goal-amount')?.value) || 0;
      await API.setDailyGoal({ goal: amount, enabled: amount > 0 });
      App.toast('Daily goal updated', 'success');
    } catch (e) {
      App.toast('Goal update failed: ' + e.message, 'error');
    }
  },

  async runBacktest() {
    const ticker = App.state.activeTicker;
    const days = parseInt(prompt('Days to backtest?', '30')) || 30;
    App.toast('Running ' + days + 'd backtest for ' + ticker + '...', 'info');
    try {
      const data = await API.backtest({ ticker, days });
      const el = byId('backtest-results');
      if (el) el.innerHTML = '<pre style="font-size:11px;white-space:pre-wrap">' + JSON.stringify(data, null, 2) + '</pre>';
      App.toast('Backtest complete', 'success');
    } catch (e) {
      App.toast('Backtest failed: ' + e.message, 'error');
    }
  },

  async createBackup() {
    App.toast('Creating backup...', 'info');
    try {
      const data = await API.createBackup();
      App.toast('Backup created: ' + (data.backup || 'success'), 'success');
    } catch (e) {
      App.toast('Backup failed: ' + e.message, 'error');
    }
  },

  // ── Notifications ──
  // ACTUAL API: {status, settings: {notif_smtp_host, notif_smtp_port, notif_smtp_user,
  //               notif_smtp_pass, notif_email_enabled, notif_email_recipient}}
  async refreshNotifications() {
    try {
      const data = await API.notifications();
      const s = data.settings || data;
      setInput('notif-smtp-host', s.notif_smtp_host);
      setInput('notif-smtp-port', s.notif_smtp_port);
      setInput('notif-smtp-user', s.notif_smtp_user);
      setInput('notif-smtp-pass', s.notif_smtp_pass);
      setCheckbox('notif-email-enabled', s.notif_email_enabled === 'true' || s.notif_email_enabled === true);
      setInput('notif-email-recipient', s.notif_email_recipient);
    } catch (e) { /* silent */ }
  },

  async saveNotifications() {
    try {
      const payload = {
        smtp_host: byId('notif-smtp-host')?.value,
        smtp_port: parseInt(byId('notif-smtp-port')?.value) || 1025,
        smtp_user: byId('notif-smtp-user')?.value,
        smtp_pass: byId('notif-smtp-pass')?.value,
        email_enabled: byId('notif-email-enabled')?.checked ?? false,
        email_recipient: byId('notif-email-recipient')?.value,
      };
      await API.setNotifications(payload);
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
      const items = data.optimizations || data.suggestions || [];
      if (items.length === 0) {
        container.innerHTML = '<p style="color:var(--text-secondary)">No optimization suggestions</p>';
        return;
      }
      container.innerHTML = items.map((o, i) =>
        '<div class="glass-panel" style="padding:10px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">' +
          '<div style="font-size:12px">' +
            '<b>' + (o.id || o.title || ('Suggestion #' + (i + 1))) + '</b> ' +
            '<span style="color:var(--text-secondary)">' + (o.description || o.title || '') + '</span>' +
          '</div>' +
          '<button class="btn btn-sm" onclick="Settings.applyOne(\'' + (o.id || '') + '\')">Apply</button>' +
        '</div>'
      ).join('');
    } catch (e) { /* silent */ }
  },

  async applyOne(id) {
    try {
      await API.applyOptimization(id);
      App.toast('Applied: ' + id, 'success');
      this.refreshOpts();
    } catch (e) {
      App.toast('Apply failed: ' + e.message, 'error');
    }
  },

  async applyAll() {
    App.toast('Applying all optimizations...', 'info');
    try {
      await API.applyAllOptimizations();
      App.toast('All optimizations applied', 'success');
      this.refreshOpts();
    } catch (e) {
      App.toast('Apply failed: ' + e.message, 'error');
    }
  },

  async review() {
    App.toast('Reviewing optimizations...', 'info');
    try {
      await API.reviewOptimization();
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
