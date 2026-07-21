#!/bin/bash
pkill -9 -f "main.py" 2>/dev/null
sleep 3
cd /root/nexustrader
nohup /root/nexustrader/venv/bin/python3 main.py --headless > /tmp/nx_live5.log 2>&1 &
sleep 10
echo "ERRORS: $(grep -c ERROR /tmp/nx_live5.log 2>/dev/null)"
tail -3 /tmp/nx_live5.log
