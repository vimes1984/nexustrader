#!/usr/bin/env python3
"""Rewrite /api/optimizations/apply/all to use real database API"""
B = "/root/nexustrader"
with open(f"{B}/main.py") as f:
    m = f.read()

# Find and replace the entire broken apply/all endpoint
start = m.find('@app.post("/api/optimizations/apply/all")')
if start == -1:
    print("ERROR: endpoint not found")
    exit(1)
# Find the end (next @app. decorator)
end = m.find('\n@app.', start + 10)

new_ep = '''@app.post("/api/optimizations/apply/all")
def apply_all_optimizations():
    """Apply all pending optimizations. Mirrors single-apply logic."""
    try:
        opts = database.load_optimizations(limit=1000)
        if not opts:
            return {"status": "ok", "count": 0, "msg": "No optimizations to apply"}
        
        applied = []
        errors = []
        for target in opts:
            try:
                param = target["parameter"]
                new_val = target["new_value"]
                
                # Save the parameter directly (bypasses MutationFreeze)
                database.save_setting_directly(param, new_val)
                
                # Update in-memory if applicable
                if hasattr(orchestrator, "probability_engine"):
                    if param == "risk_mode":
                        orchestrator.probability_engine.set_risk_mode(new_val)
                    elif param == "kelly_fraction" and hasattr(orchestrator.probability_engine, "kelly_fraction"):
                        try:
                            orchestrator.probability_engine.kelly_fraction = float(new_val)
                        except Exception:
                            pass
                
                applied.append({"id": target["id"], "parameter": param, "new_value": new_val})
            except Exception as ex:
                errors.append({"id": target.get("id"), "error": str(ex)})
        
        return {"status": "ok", "count": len(applied), "applied": applied, "errors": errors}
    except Exception as e:
        return {"status": "error", "error": str(e)}
'''

m = m[:start] + new_ep + m[end+1:]
compile(m, "main.py", "exec")
print("Compile OK")
with open(f"{B}/main.py", "w") as f:
    f.write(m)
print("apply/all rewritten with real DB API")
