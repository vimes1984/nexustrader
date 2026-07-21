/**
 * api.js — API client for NexusTrader Dashboard v3
 * All backend communication goes through this module.
 */
const API = {
  base: '',

  async _fetch(path, opts = {}) {
    const url = this.base + path;
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
    }
    return res.json();
  },

  get(path) { return this._fetch(path); },
  post(path, body) { return this._fetch(path, { method: 'POST', body: JSON.stringify(body || {}) }); },
  put(path, body) { return this._fetch(path, { method: 'PUT', body: JSON.stringify(body || {}) }); },
  delete(path) { return this._fetch(path, { method: 'DELETE' }); },

  // ── Core ──
  status()                    { return this.get('/api/status'); },
  initState()                 { return this.get('/api/status'); },
  history(ticker)             { return this.get(`/api/history?ticker=${encodeURIComponent(ticker)}`); },
  portfolioHistory()          { return this.get('/api/portfolio/history'); },
  tickers()                   { return this.get('/api/tickers'); },
  positions()                 { return this.get('/api/positions'); },
  trades()                    { return this.get('/api/trades'); },
  allTrades()                 { return this.get('/api/trades/all'); },
  shadowTrades()              { return this.get('/api/trades/shadow'); },
  shadowPerformance()         { return this.get('/api/trades/shadow/performance'); },
  weights()                   { return this.get('/api/weights'); },
  weightsHistory()            { return this.get('/api/weights/history'); },
  safetyStatus()              { return this.get('/api/safety/status'); },
  signals()                   { return this.get('/api/trading/signals'); },
  health()                    { return this.get('/api/health'); },

  // ── Control ──
  control(action)             { return this.post('/api/control', { action }); },
  setRiskMode(mode)           { return this.post('/api/risk/mode', { mode }); },

  // ── Training ──
  train()                     { return this.post('/api/training/run'); },
  trainingStatus()            { return this.get('/api/training/status'); },
  trainBrain(ticker)          { return this.post('/api/neural/train', { ticker }); },
  brains()                    { return this.get('/api/neural/brains'); },
  saveBrain(ticker, weights)  { return this.post('/api/neural/save', { ticker, weights }); },
  brainSpecs()                { return this.get('/api/neural/specs'); },
  setAutoSwitch(data)         { return this.post('/api/neural/brain/auto_switch', data); },
  autoSwitchStatus()          { return this.get('/api/neural/brain/auto_switch'); },
  runNnTests()                { return this.post('/api/neural/tests'); },
  saveArch(data)              { return this.post('/api/neural/architecture', data); },

  // ── Assets ──
  assetList()                 { return this.get('/api/tickers'); },
  addAsset(ticker)            { return this.post('/api/tickers/add', { ticker }); },
  removeAsset(ticker)         { return this.post('/api/tickers/remove', { ticker }); },
  checkExchange()             { return this.get('/api/exchange/check'); },

  // ── LLM ──
  llmStatus()                 { return this.get('/api/llm/status'); },
  llmConfig()                 { return this.get('/api/llm/config'); },
  setLlmConfig(data)          { return this.post('/api/llm/config', data); },
  llmTest(data)               { return this.post('/api/llm/test', data); },
  llmSentiment(ticker)        { return this.post('/api/llm/sentiment', { ticker }); },
  llmRegime(ticker)           { return this.post('/api/llm/regime', { ticker }); },

  // ── Agents ──
  quantStatus()               { return this.get('/api/quant/status'); },
  triggerQuant(agent)         { return this.post('/api/quant/trigger', { agent }); },
  agentRuns()                 { return this.get('/api/agents/runs'); },
  agentLlm()                  { return this.get('/api/system/agent_llm'); },
  setAgentLlm(data)           { return this.post('/api/system/agent_llm', data); },
  prompts()                   { return this.get('/api/system/prompts'); },
  savePrompt(data)            { return this.post('/api/system/prompts', data); },
  saveQuantPrompt(data)       { return this.post('/api/quant/prompt/save', data); },

  // ── Settings ──
  settings()                  { return this.get('/api/status'); },
  saveSetting(key, value)     { return this.post('/api/system/settings', { key, value }); },
  setSchedule(data)           { return this.post('/api/schedule', data); },
  schedule()                  { return this.get('/api/schedule'); },
  brokerConfig()              { return this.get('/api/system/broker_config'); },
  setBrokerConfig(data)       { return this.post('/api/system/broker_config', data); },
  testBroker()                { return this.post('/api/system/broker_test'); },
  dailyGoal()                 { return this.get('/api/system/daily_goal'); },
  setDailyGoal(data)          { return this.post('/api/system/daily_goal', data); },
  backtest()                  { return this.post('/api/backtest'); },
  createBackup()              { return this.post('/api/backup/create'); },
  backups()                   { return this.get('/api/backups'); },

  // ── Notifications ──
  notifConfig()               { return this.get('/api/notifications/config'); },
  setNotifConfig(data)        { return this.post('/api/notifications/config', data); },
  testNotif()                 { return this.post('/api/notifications/test'); },

  // ── Optimizations ──
  optimizations()             { return this.get('/api/system/optimizations'); },
  applyOptimization(id)       { return this.post(`/api/optimizations/apply/${id}`); },
  applyAllOptimizations()     { return this.post('/api/optimizations/apply/all'); },
  reviewOptimizations()       { return this.post('/api/optimizations/review'); },
  optimizeParams()            { return this.post('/api/system/optimize/params'); },
  optimizeLongTerm()          { return this.post('/api/system/optimize/longterm'); },
  triggerSelfDev()            { return this.post('/api/system/optimize/self_dev'); },
  triggerNnOptimize()         { return this.post('/api/system/optimize/nn'); },
  triggerSentiment()          { return this.post('/api/system/optimize/sentiment'); },
  triggerRiskAudit()          { return this.post('/api/system/optimize/risk_audit'); },
  triggerAllocator()          { return this.post('/api/system/optimize/allocator'); },

  // ── System / Logs ──
  systemLogs(limit)           { return this.get(`/api/system/logs?limit=${limit || 200}`); },
  logNotification(data)       { return this.post('/api/notify', data); },
  gatewayStatus()             { return this.get('/api/gateway/status'); },
  gatewayPrompt(data)         { return this.post('/api/gateway/prompt', data); },
  reasoning(data)             { return this.post('/api/gateway/reasoning', data); },
  generateBlog(data)          { return this.post('/api/blog/generate', data); },
  blogConfig()                { return this.get('/api/blog/config'); },
  setBlogConfig(data)         { return this.post('/api/blog/config', data); },

  // ── Architecture ──
  architecture()              { return this.get('/api/system/architecture'); },
};
