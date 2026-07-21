/**
 * settings.js v3 — Trading System settings tab
 */
const Settings = {
  init() {
    document.addEventListener('nt:tabChange', (e) => { if (e.detail === 'settings') this.refresh(); });
    byId('btn-save-config')?.addEventListener('click', () => this.saveConfig());
    byId('btn-reset-cooldowns')?.addEventListener('click', () => this.resetCooldowns());
    byId('btn-save-broker')?.addEventListener('click', () => this.saveBroker());
    byId('btn-test-broker')?.addEventListener('click', () => this.testBroker());
    byId('btn-set-daily-goal')?.addEventListener('click', () => this.setDailyGoal());
    byId('btn-backtest')?.addEventListener('click', () => this.runBacktest());
    byId('btn-create-backup')?.addEventListener('click', () => this.createBackup());
  },

  async refresh() {
    await Promise.all([this.loadConfig(), this.loadBroker(), this.loadDailyGoal()]);
  },

  async loadConfig() {
    try {
      const data = await API.settings();
      if (!data) return;
      setInput('config-max-position', data.max_position_size);
      setInput('config-max-drawdown', data.max_drawdown_pct);
      setInput('config-cooldown', data.cooldown_minutes);
      setInput('config-tp', data.tp_multiplier);
      setInput('config-sl', data.sl_multiplier);
    } catch(e) {}
  },

  async saveConfig() {
    try {
      const entries = [
        ['max_position_size', getInput('config-max-position')],
        ['max_drawdown_pct', getInput('config-max-drawdown')],
        ['cooldown_minutes', getInput('config-cooldown')],
        ['tp_multiplier', getInput('config-tp')],
        ['sl_multiplier', getInput('config-sl')],
      ];
      for (const [k, v] of entries) {
        if (v) await API.saveSetting(k, v);
      }
      App.toast('Configuration saved', 'success');
    } catch(e) { App.toast('Save failed: ' + e.message, 'error'); }
  },

  async resetCooldowns() {
    try { await API.saveSetting('reset_cooldowns', '1'); App.toast('Cooldowns reset', 'success'); }
    catch(e) { App.toast('Reset failed: ' + e.message, 'error'); }
  },

  async loadBroker() {
    try {
      const data = await API.brokerConfig();
      if (!data) return;
      setInput('config-broker-type', data.broker_type || 'kraken');
      setInput('config-broker-key', data.api_key || '');
      setInput('config-broker-secret', data.api_secret || '');
      byId('config-trading-mode').value = data.trading_mode || 'paper';
      const statusEl = byId('broker-status-display');
      if (statusEl && data.connected !== undefined) {
        statusEl.innerHTML = data.connected
          ? '<span class="broker-status-ok">✅ Connected to ' + (data.broker_type || 'kraken').toUpperCase() + '</span>'
          : '<span class="broker-status-fail">❌ Not connected</span>';
      }
    } catch(e) {}
  },

  async saveBroker() {
    try {
      const data = {
        broker_type: getInput('config-broker-type'),
        api_key: getInput('config-broker-key'),
        api_secret: getInput('config-broker-secret'),
        trading_mode: getInput('config-trading-mode'),
      };
      await API.setBrokerConfig(data);
      App.toast('Broker config saved', 'success');
      this.loadBroker();
    } catch(e) { App.toast('Save broker failed: ' + e.message, 'error'); }
  },

  async testBroker() {
    App.toast('Testing broker connection...', 'info');
    try {
      const data = await API.testBroker();
      if (data.ok || data.status === 'success' || data.connected) {
        App.toast('Broker connection successful! ' + (data.balance ? '$' + data.balance : ''), 'success');
      } else {
        App.toast('Broker test failed: ' + (data.error || data.message || 'Unknown'), 'error');
      }
    } catch(e) { App.toast('Broker test error: ' + e.message, 'error'); }
  },

  async loadDailyGoal() {
    try {
      const data = await API.dailyGoal();
      if (!data) return;
      setInput('daily-goal-amount', data.daily_income_goal ?? data.goal ?? data.amount ?? '');
      setCheckbox('daily-goal-enabled', data.enabled ?? true);
      const s = byId('daily-goal-status');
      if (s) s.textContent = (data.current_progress ? `Progress: $${data.current_progress} / $${data.daily_income_goal || data.goal || '?'}` : 'No active goal');
    } catch(e) {}
  },

  async setDailyGoal() {
    try {
      const amount = parseFloat(getInput('daily-goal-amount'));
      if (isNaN(amount) || amount <= 0) { App.toast('Enter a valid amount', 'error'); return; }
      const enabled = byId('daily-goal-enabled')?.checked ?? true;
      await API.setDailyGoal({ daily_income_goal: amount, enabled });
      App.toast('Daily goal set: $' + amount, 'success');
      this.loadDailyGoal();
    } catch(e) { App.toast('Set goal failed: ' + e.message, 'error'); }
  },

  async runBacktest() {
    const el = byId('backtest-results'); if (el) el.innerHTML = '<span style="color:var(--text-muted)">⏳ Running backtest...</span>';
    App.toast('Running backtest...', 'info');
    try {
      const data = await API.backtest();
      if (el) el.innerHTML = '<pre style="font-size:10px;white-space:pre-wrap;max-height:280px;overflow-y:auto;color:var(--text-primary)">' + JSON.stringify(data, null, 2).replace(/</g,'&lt;') + '</pre>';
      App.toast('Backtest complete', 'success');
    } catch(e) {
      if (el) el.innerHTML = '<span style="color:var(--neon-red)">❌ ' + e.message + '</span>';
      App.toast('Backtest failed: ' + e.message, 'error');
    }
  },

  async createBackup() {
    App.toast('Creating backup...', 'info');
    try {
      const data = await API.createBackup();
      App.toast('Backup created: ' + (data.file || data.backup || 'OK'), 'success');
    } catch(e) { App.toast('Backup failed: ' + e.message, 'error'); }
  },
};

document.addEventListener('DOMContentLoaded', () => Settings.init());
