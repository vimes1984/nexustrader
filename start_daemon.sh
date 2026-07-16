#!/bin/bash
# NexusTrader background daemon startup script

# Find the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check if port 8000 is already in use
PID=$(lsof -t -i:8000)
if [ -n "$PID" ]; then
  echo "Stopping existing NexusTrader running on port 8000 (PID: $PID)..."
  kill -9 $PID
  sleep 1
fi

echo "Starting NexusTrader in the background..."
nohup ./dist/nexustrader --headless > nexustrader_log.txt 2>&1 &

echo "--------------------------------------------------"
echo "NexusTrader started successfully in background!"
echo "PID: $!"
echo "Port: 8000"
echo "Log file: nexustrader_log.txt"
echo "--------------------------------------------------"
