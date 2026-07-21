#!/bin/bash
pkill -9 -f "main.py" 2>/dev/null
sleep 3
cd /root/nexustrader
nohup /root/nexustrader/venv/bin/python3 main.py --headless > /tmp/nx_live6.log 2>&1 &
sleep 8
echo "ERRORS: $(grep -c ERROR /tmp/nx_live6.log 2>/dev/null)"
echo "Strategies: $(grep -c strategy /tmp/nx_live6.log | head -1)"
tail -3 /tmp/nx_live6.log
