#!/usr/bin/env python3
"""Fix the OpenClaw review endpoint — wrong host, path, model"""
B = "/root/nexustrader"
with open(f"{B}/main.py") as f:
    m = f.read()

# The broken review endpoint uses localhost:18789/api/chat/completions
# Fix: use openclaw_bridge module with correct URL/path/token/model
old_review = '''        # Call OpenClaw Gateway API
        gateway_url = "http://localhost:18789/api/chat/completions"
        gateway_token = None
        import json, os
        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
                gateway_token = cfg.get("gateway", {}).get("auth", {}).get("token", "")
        
        headers = {"Content-Type": "application/json"}
        if gateway_token:
            headers["Authorization"] = f"Bearer {gateway_token}"
        
        payload = {
            "model": "deepseek/deepseek-v4-flash",
            "messages": [{"role": "user", "content": "\\n".join(prompt_lines)}],
            "max_tokens": 1024
        }
        
        resp = http_req.post(gateway_url, json=payload, headers=headers, timeout=30)'''

new_review = '''        # Call OpenClaw Gateway via bridge module
        from openclaw_bridge import query_openclaw, DEFAULT_GATEWAY_URL, DEFAULT_GATEWAY_TOKEN
        import json
        
        gateway_url = DEFAULT_GATEWAY_URL
        gateway_token = DEFAULT_GATEWAY_TOKEN
        
        headers = {"Content-Type": "application/json"}
        if gateway_token:
            headers["Authorization"] = f"Bearer {gateway_token}"
        
        payload = {
            "model": "openclaw",
            "messages": [{"role": "user", "content": "\\n".join(prompt_lines)}],
            "max_tokens": 1024
        }
        
        resp = http_req.post(gateway_url, json=payload, headers=headers, timeout=30)'''

m = m.replace(old_review, new_review)

# Also fix the response parsing — it might error with different format
old_parse = '        review_text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "No response")'
new_parse = '        review_text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "No response. Gateway returned: " + str(resp.status_code))'
m = m.replace(old_parse, new_parse)

compile(m, "main.py", "exec")
print("Compile OK")
with open(f"{B}/main.py", "w") as f:
    f.write(m)
print("Fixed: OpenClaw review now uses bridge module (192.168.0.197:18789/v1, model=openclaw, correct token)")
