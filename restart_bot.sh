#!/bin/bash
pkill -9 -f "main.py" 2>/dev/null
sleep 2
cd /root/nexustrader
nohup /root/nexustrader/venv/bin/python3 main.py --headless > /tmp/nx_live4.log 2>&1 &
sleep 6
echo "ERRORS: $(grep -c ERROR /tmp/nx_live4.log 2>/dev/null)"
tail -2 /tmp/nx_live4.log
