#!/usr/bin/env python3
"""Check API endpoints."""
import urllib.request, json

for name, url in [
    ("status", "http://localhost:8000/api/status"),
    ("safety", "http://localhost:8000/api/safety/status"),
    ("init", "http://localhost:8000/api/init"),
]:
    try:
        r = json.loads(urllib.request.urlopen(url, timeout=5).read())
        print(f"=== /api/{name} ===")
        for k in sorted(r.keys()):
            v = r[k]
            if isinstance(v, dict):
                v = f"dict({len(v)})"
            elif isinstance(v, list):
                v = f"list({len(v)})"
            elif isinstance(v, float):
                v = round(v, 4)
            print(f"  {k}: {v}")
        print()
    except Exception as e:
        print(f"/api/{name}: {e}")
