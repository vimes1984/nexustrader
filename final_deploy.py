#!/usr/bin/env python3
"""Final deploy: kill, start, verify bot stays alive."""
import os, subprocess, time, json, urllib.request

HOST = "192.168.0.144"
LOG = "/tmp/nexustrader_live.log"

def ssh(cmd):
    return subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
         f"root@{HOST}", cmd],
        capture_output=True, text=True, timeout=60
    )

# Kill everything
print("Killing old processes...")
ssh("pkill -9 -f main.py 2>/dev/null; sleep 3; echo done")

# Start fresh
print("Starting bot...")
r = ssh("cd /root/nexustrader && nohup /root/nexustrader/venv/bin/python3 main.py --headless > /tmp/nexustrader_live.log 2>&1 & echo PID=$!")
print(r.stdout.strip())

# Wait for startup
print("Waiting 40s for startup...")
time.sleep(40)

# Check endpoints
print("\n=== Endpoints ===")
for ep in ["/api/status", "/api/init", "/api/trading/signals", "/api/trading/reasoning", "/api/safety/status"]:
    try:
        r = ssh(f"curl -s http://localhost:8000{ep} 2>/dev/null || /root/nexustrader/venv/bin/python3 -c \"import urllib.request,json; print(json.loads(urllib.request.urlopen('http://localhost:8000{ep}',timeout=5).read()))\" 2>/dev/null")
        output = r.stdout.strip()
        # Check if it has balance or items
        if "balance" in output or "items" in output or "kill_switch" in output:
            print(f"  {ep}: OK")
        else:
            print(f"  {ep}: {output[:100]}")
    except Exception as e:
        print(f"  {ep}: FAIL - {e}")

# Check alive
print("\n=== Alive check ===")
r = ssh("ps aux | grep 'main.py' | grep -v grep | wc -l")
procs = int(r.stdout.strip())
print(f"  Processes: {procs}")

r = ssh("lsof -i :8000 | grep LISTEN | wc -l")
ports = int(r.stdout.strip())
print(f"  Port 8000: {ports} listening")

# Check errors
r = ssh("grep -c 'ERROR' /tmp/nexustrader_live.log 2>/dev/null || echo 0")
errors = int(r.stdout.strip())
print(f"  Errors: {errors}")

# Check signals are non-zero
r = ssh("grep -c 'sqlite3.Row' /tmp/nexustrader_live.log 2>/dev/null || echo 0")
row_errors = int(r.stdout.strip())
print(f"  sqlite3.Row errors: {row_errors}")

# Get signal data
r = ssh("/root/nexustrader/venv/bin/python3 -c \"import urllib.request,json; r=json.loads(urllib.request.urlopen('http://localhost:8000/api/trading/signals',timeout=5).read()); [print(k+': '+v.get('direction','?')+' ws='+str(round(v.get('weighted_signal',0),4))) for k,v in sorted(r.items())]\"")
print(f"\n=== Signals ===\n{r.stdout}")

# Wait 30s and recheck
print("Waiting 30s to verify stability...")
time.sleep(30)

r = ssh("ps aux | grep 'main.py' | grep -v grep | wc -l")
procs2 = int(r.stdout.strip())
print(f"  After 30s: {procs2} processes")
if procs2 >= 1:
    print("✓ Bot is STABLE and ALIVE")
else:
    print("✗ Bot died!")
    r = ssh("tail -5 /tmp/nexustrader_live.log")
    print(f"  Last log lines: {r.stdout}")
