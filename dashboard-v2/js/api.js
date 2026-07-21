/**
 * api.js — Unified API client for NexusTrader Dashboard v2
 * Single source of truth for all backend communication.
 */

const API = {
  BASE: '',

  /** Generic JSON request with timeout + error handling */
  async request(method, path, body = null, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const opts = {
        method,
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
      };
      if (body && method !== 'GET') opts.body = JSON.stringify(body);
      const res = await fetch(API.BASE + path, opts);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  },

  get(path)  { return this.request('GET', path); },
  post(path, body) { return this.request('POST', path, body); },
  put(path, body)  { return this.request('PUT', path, body); },

  // ── Status & Init ──
  status()       { return this.get('/api/status'); },
  initState()    { return this.get('/api/init'); },
  health()       { return this.get('/api/health'); },
  safetyStatus() { return this.get('/api/safety/status'); },

  // ── Trading ──
  trades(ticker, limit = 50) { return this.get(`/api/trades?ticker=${ticker}&limit=${limit}`); },
  allTrades()                 { return this.get('/api/trades/all'); },
  signals()                   { return this.get('/api/trading/signals'); },
  reasoning()                 { return this.get('/api/trading/reasoning'); },
  positions()                 { return this.get('/api/positions'); },
  history(ticker)             { return this.get(`/api/history?ticker=${ticker}`); },
  portfolioHistory()          { return this.get('/api/portfolio/history'); },
  weights()                   { return this.get('/api/weights'); },
  weightsHistory()            { return this.get('/api/weights/history'); },
  control(action)             { return this.post('/api/control', { action }); },

  // ── Neural / Brains ──
  brains()                    { return this.get('/api/neural/brains'); },
  brainSpecs()                { return this.get('/api/neural/brain/specs'); },
  activateBrain(ticker, brain) { return this.post('/api/neural/brain/activate', { ticker, brain }); },
  autoSwitchStatus()          { return this.get('/api/neural/brain/auto_switch'); },
  setAutoSwitch(enabled)      { return this.post('/api/neural/brain/auto_switch', { enabled }); },
  saveBrain(data)             { return this.post('/api/neural/brain/save', data); },
  deleteBrain(name)           { return this.post('/api/neural/brain/delete', { name }); },
  trainBrain(ticker)          { return this.post('/api/neural/brain/train', { ticker }); },
  nnArchitecture()            { return this.get('/api/nn/architecture'); },
  setNnArchitecture(data)     { return this.post('/api/nn/architecture', data); },
  runNnTests()                { return this.post('/api/nn/tests'); },

  // ── Historical Training ──
  runTraining(ticker, days = 30, epochs = 20) {
    return this.post('/api/training/run', { ticker, days, epochs });
  },

  // ── Assets ──
  assets()                    { return this.get('/api/assets'); },
  saveAsset(data)             { return this.post('/api/assets/save', data); },
  deleteAsset(ticker)         { return this.post('/api/assets/delete', { ticker }); },
  exchangeStatus()            { return this.get('/api/exchange/status'); },

  // ── LLM ──
  llmStatus()                 { return this.get('/api/llm/status'); },
  llmTest(data)               { return this.post('/api/llm/test', data); },
  llmSentiment(ticker)        { return this.post('/api/llm/sentiment', { ticker }); },
  llmRegime(ticker)           { return this.post('/api/llm/regime', { ticker }); },
  llmConfig()                 { return this.get('/api/llm/config'); },
  setLlmConfig(data)          { return this.post('/api/llm/config', data); },

  // ── Quant Team / Agents ──
  quantStatus()               { return this.get('/api/quant/status'); },
  triggerQuant(agent)         { return this.post('/api/quant/trigger', { agent }); },
  saveQuantPrompt(data)       { return this.post('/api/quant/prompt/save', data); },
  agentRuns()                 { return this.get('/api/system/agent_runs'); },
  agentLlm()                  { return this.get('/api/system/agent_llm'); },
  setAgentLlm(data)           { return this.post('/api/system/agent_llm', data); },
  prompts()                   { return this.get('/api/system/prompts'); },
  savePrompt(data)            { return this.post('/api/system/prompts', data); },

  // ── System / Settings ──
  systemConfig()              { return this.get('/api/system/config'); },
  setSystemConfig(data)       { return this.post('/api/system/config', data); },
  saveSetting(data)           { return this.post('/api/system/save_setting', data); },
  setRiskMode(mode)           { return this.post('/api/system/risk_mode', { mode }); },
  testBroker()                { return this.get('/api/system/test_broker'); },
  resetCooldowns()            { return this.post('/api/system/reset_cooldowns'); },
  dailyGoal()                 { return this.get('/api/system/daily_goal'); },
  setDailyGoal(data)          { return this.post('/api/system/daily_goal', data); },

  // ── Notifications ──
  notifications()             { return this.get('/api/system/notifications'); },
  setNotifications(data)      { return this.post('/api/system/notifications', data); },
  testNotification()          { return this.post('/api/system/notifications/test'); },
  logNotification(data)       { return this.post('/api/system/log_notification', data); },

  // ── Optimization ──
  optimizations()             { return this.get('/api/system/optimizations'); },
  applyOptimization(id)       { return this.post(`/api/optimizations/apply/${id}`); },
  applyAllOptimizations()     { return this.post('/api/optimizations/apply/all'); },
  reviewOptimization()        { return this.post('/api/optimizations/review'); },
  optimizeParameters()        { return this.post('/api/system/optimize/parameters'); },
  optimizeLongTerm()          { return this.post('/api/system/optimize/long_term'); },
  triggerSelfDev()            { return this.post('/api/system/optimize/self_dev'); },
  triggerNnOptimize()         { return this.post('/api/system/optimize/nn'); },
  triggerSentiment()          { return this.post('/api/system/optimize/sentiment'); },
  triggerRiskAudit()          { return this.post('/api/system/optimize/risk_audit'); },
  triggerAllocator()          { return this.post('/api/system/optimize/allocator'); },

  // ── Backtest ──
  backtest(data)              { return this.post('/api/system/backtest', data); },

  // ── Shadow Trading ──
  shadowTrades()              { return this.get('/api/system/shadow_trades'); },
  shadowPerformance()         { return this.get('/api/system/shadow_performance'); },

  // ── Backups ──
  createBackup()              { return this.post('/api/system/backup'); },
  backups()                   { return this.get('/api/system/backups'); },
  restoreBackup(filename)     { return this.post(`/api/system/backup/restore/${filename}`); },

  // ── Gateway ──
  gatewayStatus()             { return this.get('/api/gateway/status'); },
  gatewayPrompt(prompt)       { return this.post('/api/gateway/prompt', { prompt }); },

  // ── Blog ──
  blogConfig()                { return this.get('/api/blog/config'); },
  setBlogConfig(data)         { return this.post('/api/blog/config', data); },
  generateBlog()              { return this.post('/api/blog/generate'); },

  // ── Schedule ──
  schedule()                  { return this.get('/api/system/schedule'); },
  setSchedule(data)           { return this.post('/api/system/schedule', data); },

  // ── Logs ──
  systemLogs(limit = 200)     { return this.get(`/api/system/logs?limit=${limit}`); },
};

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = API;
}
