#!/bin/bash

# NexusTrader Desktop App Runner
# Starts the backend server and opens the browser interface automatically.

echo "============================================="
echo "🚀 Starting NexusTrader Standalone Application..."
echo "============================================="

# Identify working directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Launch NexusTrader in the background (headless daemon mode)
echo "🤖 Starting API & Ingestion Engine on port 8000..."
python3 main.py --headless > nexustrader_log.txt 2>&1 &
SERVER_PID=$!

# Trap Ctrl+C to clean up the backend process automatically
cleanup() {
    echo ""
    echo "🛑 Shutting down NexusTrader backend server (PID $SERVER_PID)..."
    kill $SERVER_PID
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for server to boot up
sleep 2

# Verify server is running
if ps -p $SERVER_PID > /dev/null; then
    echo "✅ Server started successfully!"
    echo "🌐 Opening dashboard in your default browser..."
    
    # Auto-open browser on Linux
    if command -v xdg-open > /dev/null; then
        xdg-open "http://localhost:8000"
    else
        echo "Please open http://localhost:8000 manually in your browser."
    fi
    
    echo "============================================="
    echo "🟢 NexusTrader is running continuously."
    echo "👉 Press Ctrl+C in this terminal window to stop the application."
    echo "============================================="
    
    # Keep script alive to maintain process ownership
    wait $SERVER_PID
else
    echo "❌ Failed to start the backend server."
    echo "Please check nexustrader_log.txt for error details."
    exit 1
fi
