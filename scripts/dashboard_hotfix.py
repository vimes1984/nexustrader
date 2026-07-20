#!/usr/bin/env python3
from pathlib import Path
ROOT = Path('/root/.openclaw/workspace/nexustrader')
MAIN = ROOT / 'main.py'
s = MAIN.read_text()

changes = []

old_ws = 'for i in range(len(ensemble.weights))'
new_ws = 'for i in range(min(len(ensemble.weights), len(ensemble.strategies)))'
if old_ws in s:\n    s = s.replace(old_ws, new_ws, 1)\n    changes.append('WS weights range(len)->min(len)')\nelse:
    changes.append('WS weights already patched (no-op)')

old_get = 'trades = _db.get_trades(limit=100)'
new_get = 'trades = _db.load_trades()'
if old_get in s:\n    s = s.replace(old_get, new_get, 1)\n    changes.append('get_trades->load_trades in /api/trades/all')\nelse:
    changes.append('trades/all already uses load_trades (no-op)')

if '@app.get("/api/trading/reasoning")' not in s:\n    marker = '@app.get("/api/trading/signals")'
    if marker not in s:\n        marker = '@app.get("/api/init")'
    route = (Path('/tmp/reasoning_route.txt').read_text().strip() + '\n\n')
    s = s.replace(marker, route + marker, 1)
    changes.append('reasoning endpoint added')
else:
    changes.append('reasoning already exists (no-op)')

compile(s, str(MAIN), 'exec')
MAIN.write_text(s)
for c in changes:\n    print('OK:', c)\nPYEOF\ncd /root/.openclaw/workspace/nexustrader && python3 scripts/dashboard_hotfix.py && echo '=== compile check ===' && python3 -m py_compile main.py && echo PASS