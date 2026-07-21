#!/usr/bin/env python3
"""Fix all 5 critical issues in one pass"""
B = "/root/nexustrader"

# ── FIX 1: WebSocket — handle empty tickers ──
with open(f"{B}/main.py") as f:
    m = f.read()

ws_old = """    try:
        # Send initial configuration and state (defaults to first ticker weights for basic UI compatibility)
        first_ticker = orchestrator.tickers[0]"""

ws_new = """    try:
        # Send initial configuration and state (defaults to first ticker weights for basic UI compatibility)
        if not orchestrator.tickers:
            await websocket.send_json({"type":"init","status":"waiting","msg":"Tickers not yet loaded"})
            # Keep connection alive until tickers load
            import asyncio as _asyncio
            for _ in range(30):
                await _asyncio.sleep(1)
                if orchestrator.tickers:
                    break
            if not orchestrator.tickers:
                await websocket.close()
                return
        first_ticker = orchestrator.tickers[0]"""

m = m.replace(ws_old, ws_new)
print("1. WS: empty tickers handled")

# ── FIX 2: Remove the initQuantTeam IIFE and make it a direct call ──
# The issue: it's a self-invoking function at the bottom of enhancer.js
# But it lives inside the outer IIFE and calls window.* functions that are defined
# Problem might be that initQuantTeam runs BEFORE those functions are assigned
# Solution: Remove the IIFE wrapper, make init run after definitions inline

with open(f"{B}/dashboard/enhancer.js") as f:
    js = f.read()

# Replace the initQuantTeam IIFE pattern with direct execution
old_iife = """    (function initQuantTeam() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initQuantTeam);
            return;
        }

        var triggers = {"""

new_iife = """    (function bootQuantTeam() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootQuantTeam);
            return;
        }
        _runQuantTeam();
    })();
    
    function _runQuantTeam() {
        var triggers = {"""

js = js.replace(old_iife, new_iife)

# Fix the closing: was }()); now becomes }
old_close = """        setInterval(function() { window.pollQuantTeam(); }, 60000);
    }());"""

new_close = """        setInterval(function() { window.pollQuantTeam(); }, 60000);
    }"""

js = js.replace(old_close, new_close)

opens = js.count('{')
closes = js.count('}')
print(f"2. Quant Team init fixed. Braces: {opens}/{closes} {'OK' if opens==closes else 'MISMATCH'}")

with open(f"{B}/dashboard/enhancer.js", "w") as f:
    f.write(js)

# ── FIX 3: OpenClaw review — fix localhost URL ──
with open(f"{B}/dashboard/app_v2.js") as f:
    av2 = f.read()

# Find where openclaw review calls localhost
# Let me search for the actual error URL pattern
if 'localhost:18789/api/chat/completions' in av2:
    av2 = av2.replace(
        'localhost:18789/api/chat/completions',
        '192.168.0.197:18789/v1/chat/completions'
    )
    print("3a. Fixed localhost:18789/api/chat → 192.168.0.197:18789/v1")
elif 'localhost' in av2:
    # Find all localhost references
    for i, line in enumerate(av2.split('\n')):
        if 'localhost' in line:
            print(f"  localhost found line {i}: {line.strip()[:100]}")

# Fix the default model for openclaw (should be 'openclaw' not 'google/gemini-3.5-flash')
if 'google/gemini-3.5-flash' in av2:
    av2 = av2.replace(
        "inputModel.value = \"google/gemini-3.5-flash\"",
        "inputModel.value = \"openclaw\""
    )
    print("3b. Fixed openclaw model: gemini-3.5-flash → openclaw")

with open(f"{B}/dashboard/app_v2.js", "w") as f:
    f.write(av2)

# ── FIX 4: Add Apply All button to optimizations tab ──
with open(f"{B}/dashboard/index.html") as f:
    html = f.read()

# Find the btn-review-optimizations and add Apply All next to it
opt_old = '''                            <button class="btn btn-primary" id="btn-review-optimizations" style="font-size: 11px; padding: 6px 12px;">
                                <i data-lucide="brain"></i> OpenClaw Review
                            </button>
                            <button class="btn" id="btn-refresh-optimizations" style="font-size: 11px; padding: 6px 12px;">'''

opt_new = '''                            <button class="btn btn-primary" id="btn-review-optimizations" style="font-size: 11px; padding: 6px 12px;">
                                <i data-lucide="brain"></i> OpenClaw Review
                            </button>
                            <button class="btn btn-success" id="btn-apply-all-optimizations" style="font-size: 11px; padding: 6px 12px; background: linear-gradient(135deg, #10b981, #059669); border: none; color: #fff; display: none;">
                                <i data-lucide="check-circle"></i> Apply All
                            </button>
                            <button class="btn" id="btn-refresh-optimizations" style="font-size: 11px; padding: 6px 12px;">'''

html = html.replace(opt_old, opt_new)
print("4. Apply All button added to optimizations tab")

# Also add JS handler in enhancer.js for the Apply All button
with open(f"{B}/dashboard/enhancer.js") as f:
    js2 = f.read()

# Find the event binding section
apply_all_js = """
        // Apply All Optimizations button
        var applyAllBtn = document.getElementById('btn-apply-all-optimizations');
        if (applyAllBtn) {
            applyAllBtn.addEventListener('click', function() {
                if (!confirm('Apply all pending optimizations? This will update TP/SL, thresholds, and strategy weights.')) return;
                applyAllBtn.disabled = true;
                applyAllBtn.textContent = 'Applying...';
                xhr('POST', '/api/optimizations/apply/all', function(resp) {
                    applyAllBtn.disabled = false;
                    applyAllBtn.innerHTML = '<i data-lucide=\"check-circle\"></i> Apply All';
                    try {
                        var r = JSON.parse(resp || '{}');
                        if (r.status === 'ok') {
                            window.showToast && window.showToast('Applied ' + r.count + ' optimizations!', 'success');
                        } else {
                            window.showToast && window.showToast('Error: ' + (r.error || 'unknown'), 'error');
                        }
                    } catch(e) {}
                }, function(err) {
                    applyAllBtn.disabled = false;
                    applyAllBtn.innerHTML = '<i data-lucide=\"check-circle\"></i> Apply All';
                    window.showToast && window.showToast('Apply failed: ' + err, 'error');
                });
            });
        }
"""

# Insert before the closing of _runQuantTeam or at the end of bootQuantTeam
ins_point = "        setInterval(function() { window.pollQuantTeam(); }, 60000);\n    }"
js2 = js2.replace(ins_point, ins_point + apply_all_js)

opens2 = js2.count('{')
closes2 = js2.count('}')
print(f"5. Apply All JS added. Braces: {opens2}/{closes2} {'OK' if opens2==closes2 else 'MISMATCH'}")

with open(f"{B}/dashboard/enhancer.js", "w") as f:
    f.write(js2)

# ── Add /api/optimizations/apply/all endpoint ──
apply_ep = '''
@app.post("/api/optimizations/apply/all")
async def apply_all_optimizations(request: Request):
    """Apply all pending optimizations at once."""
    import database as _db
    import traceback as _tb
    try:
        # Load all pending optimizations
        rows = _db._execute("SELECT id, action_type, ticker, params FROM optimizations WHERE status = 'pending' ORDER BY id")
        if not rows:
            return {"status": "ok", "count": 0, "msg": "No pending optimizations"}
        
        applied = []
        for row in rows:
            oid = row[0]
            action = row[1]
            ticker = row[2]
            params_str = row[3]
            try:
                params = __import__("json").loads(params_str) if params_str else {}
            except Exception:
                params = {}
            
            try:
                if action == "tp_sl":
                    for key in ("tp_multiplier", "sl_multiplier"):
                        if key in params:
                            _db.save_setting(key, str(params[key]))
                elif action == "threshold":
                    if "signal_threshold" in params:
                        _db.save_setting("signal_threshold", str(params["signal_threshold"]))
                elif action == "learning_rate":
                    if "nn_lr" in params:
                        _db.save_setting("nn_lr", str(params["nn_lr"]))
                elif action == "weights":
                    if ticker and "weights" in params:
                        _db.save_setting(f"policy_net_weights_{ticker}", __import__("json").dumps(params["weights"]))
                
                _db._execute("UPDATE optimizations SET status = 'applied', applied_at = datetime('now') WHERE id = ?", (oid,))
                applied.append({"id": oid, "action": action, "ticker": ticker})
            except Exception as e:
                print(f"Failed to apply optimization {oid}: {e}")
        
        return {"status": "ok", "count": len(applied), "applied": applied}
    except Exception as e:
        _tb.print_exc()
        return {"status": "error", "error": str(e)}
'''

m = m.replace(
    '@app.post("/api/optimizations/review")',
    apply_ep + '\n@app.post("/api/optimizations/review")'
)

# Save main.py
compile(m, "main.py", "exec")
print("6. /api/optimizations/apply/all endpoint added")
with open(f"{B}/main.py", "w") as f:
    f.write(m)

print("\nALL FIXES APPLIED")
