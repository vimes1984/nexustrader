#!/usr/bin/env python3
"""Fix stream display in reasoning endpoint."""
with open("/root/nexustrader/main.py") as f:
    m = f.read()
m = m.replace(
    '"Active" if getattr(orb, "stream_active", False) else "Stream idle"',
    '"Active" if len(getattr(orb, "latest_ticks", {})) > 0 else "Polling"'
)
# Also fix the old one
m = m.replace(
    '"Stream active" if getattr(orb, "stream_active", False) else "Stream idle"',
    '"Active" if len(getattr(orb, "latest_ticks", {})) > 0 else "Polling"'
)
with open("/root/nexustrader/main.py", "w") as f:
    f.write(m)
compile(open("/root/nexustrader/main.py").read(), "main.py", "exec")
print("Fixed stream display, syntax OK")
