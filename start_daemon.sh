#!/bin/bash
# NexusTrader background daemon startup script
# Uses port 8000 for the API server (uvicorn bind).

set -e

# Find the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Default port
PORT=8000

# Check if port is already in use
PID=$(lsof -t -i:${PORT} 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "Stopping existing NexusTrader running on port ${PORT} (PID: $PID)..."
  kill -9 $PID 2>/dev/null || true
  sleep 1
fi

# Clear previous log
> nexustrader_log.txt

echo "Starting NexusTrader on 0.0.0.0:${PORT} in the background..."
nohup python3 main.py --headless > nexustrader_log.txt 2>&1 &
BOT_PID=$!

# Wait and verify bind
for i in 1 2 3 4 5; do
  if lsof -t -i:${PORT} 2>/dev/null | grep -q .; then
    echo "✓ Server bound to port ${PORT}"
    break
  fi
  sleep 1
done

if ! lsof -t -i:${PORT} 2>/dev/null | grep -q .; then
  echo "⚠ Server may not have bound to port ${PORT}. Check nexustrader_log.txt:"
  tail -10 nexustrader_log.txt 2>/dev/null || true
fi

echo "--------------------------------------------------"
echo "NexusTrader started (PID: $BOT_PID)"
echo "API: http://0.0.0.0:${PORT}"
echo "Log: nexustrader_log.txt"
echo "Health: curl -s http://127.0.0.1:${PORT}/api/health"
echo "--------------------------------------------------"
