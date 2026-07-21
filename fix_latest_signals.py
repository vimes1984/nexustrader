#!/usr/bin/env python3
"""Fix weighted_signal reference and move start_stream to startup_event."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

# Fix 1: Change earliest reference to use default 0.0
c = c.replace(
    "self.latest_signals[ticker] = weighted_signal",
    "self.latest_signals[ticker] = 0.0"
)

# Fix 2: Add update after real computation
old = "        weighted_signal, strategy_breakdown = ensemble.get_weighted_signal(row, ingestor.data)"
new = "        weighted_signal, strategy_breakdown = ensemble.get_weighted_signal(row, ingestor.data)\n        self.latest_signals[ticker] = weighted_signal"

if old in c:
    c = c.replace(old, new)
    print("Fixed weighted_signal tracking position")
else:
    idx = c.find("get_weighted_signal(row")
    if idx >= 0:
        print(f"Found at {idx}: {c[idx:idx+80]}")

# Fix 3: Move start_stream inside startup_event
old_startup = """    # Auto-start live stream on startup (true live data)
    orchestrator.start_stream(mode="live", poll_interval=5)"""
new_startup = """    # Auto-start live stream on startup (true live data) - called in startup_event
    pass"""

if old_startup in c:
    c = c.replace(old_startup, new_startup)
    print("Moved start_stream out of module level")
else:
    idx = c.find("Auto-start live stream")
    print(f"start_stream module-level not found at {idx}")

# Add start_stream to startup_event
old_evt = "async def startup_event():\n    await orchestrator.initialize()"
new_evt = "async def startup_event():\n    await orchestrator.initialize()\n    # Start live data streaming\n    try:\n        orchestrator.start_stream(mode=\"live\", poll_interval=5)\n    except Exception as st_e:\n        logging.error(f\"Failed to start stream: {st_e}\")"

if old_evt in c:
    c = c.replace(old_evt, new_evt, 1)
    print("Added start_stream to startup_event")
else:
    idx = c.find("startup_event")
    print(f"startup_event at {idx}: {c[idx:idx+80]}")

try:
    compile(c, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(c)
    print("Saved")
except SyntaxError as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
