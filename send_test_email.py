#!/usr/bin/env python3
"""Send test email via Proton Mail Bridge."""
import smtplib
import sqlite3
import os
from email.mime.text import MIMEText
from email.utils import formatdate, formataddr

# Get bridge credentials from NexusTrader DB (on .144 via SSH)
# But since we're on .77, check local bridge config
# Proton Bridge CLI stores creds locally

# First try getting password from bridge
import subprocess
try:
    result = subprocess.run(
        [os.path.expanduser("~/.local/lib/protonmail/bridge"), "--cli", "info"],
        capture_output=True, text=True, timeout=10
    )
    print("Bridge info:", result.stdout[:200])
except Exception as e:
    print(f"Bridge CLI failed: {e}")

# Try with the known credentials from nexus trader DB
# The bridge password is stored on .144
import subprocess
result = subprocess.run(
    ["ssh", "-o", "ConnectTimeout=5", "root@192.168.0.144",
     "sqlite3 /root/.nexustrader/nexustrader.db \"SELECT value FROM settings WHERE key='proton_bridge_password'\""],
    capture_output=True, text=True, timeout=10
)
password = result.stdout.strip()
print(f"Password from DB: {'found' if password else 'NOT FOUND'}")

if not password:
    print("Cannot get bridge password")
    exit(1)

user = "Kevin_the_minion_the_nineteenth@proton.me"

body = """Hey Chris! 👋

This is a test email from OpenClaw — Kevin the Minion reporting in from the bcottage homelab!

✅ Pi-hole DNS: 13 *.bcottage domains live
✅ Nginx reverse proxy: 8 vhosts configured  
✅ bumble.cottage: WP site fixed
🔜 Home Assistant: API reachable, needs token
🔜 Router DNS: Set 192.168.0.200 as primary

— Kevin 🍌
Sent from the bcottage homelab, via OpenClaw + Proton Bridge"""

msg = MIMEText(body, "plain", "utf-8")
msg["From"] = formataddr(("Kevin the Minion", user))
msg["To"] = "churchill.c.j@gmail.com"
msg["Subject"] = "Test Email from OpenClaw / bcottage Network"
msg["Date"] = formatdate(localtime=True)

try:
    with smtplib.SMTP("127.0.0.1", 1025, timeout=15) as smtp:
        smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(msg)
    print("✅ EMAIL SENT SUCCESSFULLY!")
except Exception as e:
    print(f"❌ FAILED: {e}")
