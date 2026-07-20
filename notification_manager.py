# notification_manager.py
import sqlite3
import json
import smtplib
from email.mime.text import MIMEText
import urllib.request
import urllib.error
import logging
import database
import time
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NotificationManager")

ALERT_DB_PATH = "/root/nexustrader/data/alerts.db"

def _ensure_alerts_db():
    os.makedirs(os.path.dirname(ALERT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(ALERT_DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        severity TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp REAL NOT NULL,
        acknowledged INTEGER DEFAULT 0,
        resolved INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS health_state (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()
    conn.close()

_ensure_alerts_db()

def get_notification_settings():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    
    settings = {
        "notif_email_enabled": "false",
        "notif_email_recipient": "",
        "notif_smtp_host": "smtp.gmail.com",
        "notif_smtp_port": "587",
        "notif_smtp_user": "",
        "notif_smtp_pass": "",
        "notif_whatsapp_enabled": "false",
        "notif_whatsapp_webhook": "",
        "notif_ntfy_enabled": "false",
        "notif_ntfy_topic": "",
        "notif_ntfy_server": "https://ntfy.sh"
    }
    
    for r in rows:
        if r[0] in settings:
            settings[r[0]] = r[1]
            
    return settings

def save_notification_settings(settings_dict):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    for k, v in settings_dict.items():
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (k, str(v))
        )
    conn.commit()
    conn.close()

def push_alert(severity, category, title, message):
    """Record an alert and route to all enabled notification channels."""
    ts = time.time()
    conn = sqlite3.connect(ALERT_DB_PATH)
    conn.execute(
        "INSERT INTO alerts (severity, category, title, message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (severity, category, title, message, ts)
    )
    conn.commit()
    conn.close()
    
    # Route to notification channels
    settings = get_notification_settings()
    body = f"[{severity.upper()}] {title}\n\n{message}"
    
    if settings.get("notif_ntfy_enabled") == "true":
        _send_ntfy(settings, severity, title, message)
    
    if settings.get("notif_email_enabled") == "true":
        send_smtp_email(settings, f"NexusTrader Alert: {title}", body)
    
    if settings.get("notif_whatsapp_enabled") == "true":
        send_whatsapp_webhook(settings, body)
    
    logger.info(f"Alert [{severity}] {title}: {message}")

def get_alerts(limit=50, since_id=None):
    conn = sqlite3.connect(ALERT_DB_PATH)
    if since_id:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE id > ? ORDER BY id DESC LIMIT ?",
            (since_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "severity": r[1],
            "category": r[2],
            "title": r[3],
            "message": r[4],
            "timestamp": r[5],
            "acknowledged": bool(r[6]),
            "resolved": bool(r[7])
        }
        for r in rows
    ]

def acknowledge_alert(alert_id):
    conn = sqlite3.connect(ALERT_DB_PATH)
    conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def resolve_alert(alert_id):
    conn = sqlite3.connect(ALERT_DB_PATH)
    conn.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def get_health_state(key, default=None):
    conn = sqlite3.connect(ALERT_DB_PATH)
    row = conn.execute("SELECT value FROM health_state WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return row[0]
    return default

def set_health_state(key, value):
    conn = sqlite3.connect(ALERT_DB_PATH)
    conn.execute("INSERT OR REPLACE INTO health_state (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# ─── ntfy.sh push notifications ───────────────────────────────────────

def _send_ntfy(settings, severity, title, message):
    topic = settings.get("notif_ntfy_topic", "")
    server = settings.get("notif_ntfy_server", "https://ntfy.sh")
    if not topic:
        return False
    
    priority = 3  # default
    tags = []
    if severity == "critical":
        priority = 5
        tags = ["warning", "rotating_light"]
    elif severity == "warning":
        priority = 4
        tags = ["warning"]
    elif severity == "info":
        priority = 2
        tags = ["information"]
    
    try:
        payload = json.dumps({
            "topic": topic,
            "title": title,
            "message": message,
            "priority": priority,
            "tags": tags
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{server.rstrip('/')}/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info(f"ntfy.sh push sent: {resp.status}")
            return True
    except Exception as e:
        logger.error(f"ntfy.sh push failed: {e}")
        return False

# ─── Legacy notification routines ──────────────────────────────────────

def generate_summary_text():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('portfolio_balance', 'portfolio_live_equity', 'initial_portfolio_balance', 'daily_income_goal')")
    settings = {r[0]: r[1] for r in cursor.fetchall()}
    
    cursor.execute("SELECT COUNT(*) FROM trades")
    total_trades = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'closed'")
    closed_trades = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(pnl) FROM trades WHERE status = 'closed'")
    total_pnl = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'")
    open_trades = cursor.fetchone()[0]
    
    conn.close()
    
    balance = float(settings.get("portfolio_balance", "100.0"))
    equity = float(settings.get("portfolio_live_equity", "100.0"))
    initial_balance = float(settings.get("initial_portfolio_balance", "100.0"))
    goal = float(settings.get("daily_income_goal", "1000.0"))
    
    net_pnl = equity - initial_balance
    pnl_percent = (net_pnl / initial_balance) * 100 if initial_balance > 0 else 0.0
    
    summary = f"""🤖 NexusTrader Quant Summary Report

---
💰 Portfolio Status:
* Current Balance (Cash): ${balance:,.2f}
* Total Equity (Valuation): ${equity:,.2f}
* Initial Baseline Capital: ${initial_balance:,.2f}
* Net PnL (Life-to-Date): ${net_pnl:+,.2f} ({pnl_percent:+.2f}%)

📈 Trading Activity:
* Active Open Positions: {open_trades}
* Closed Trades Count: {closed_trades}
* Cumulative Closed PnL: ${total_pnl:+,.2f}
* Total Operations Run: {total_trades}

🎯 Quantitative Mission:
* Target Daily Income Goal: ${goal:,.2f}
---
Generated automatically by NexusTrader Neuro-Quantitative Engine.
"""
    return summary

def send_smtp_email(settings, subject, body):
    recipient = settings.get("notif_email_recipient", "")
    host = settings.get("notif_smtp_host", "smtp.gmail.com")
    port = int(settings.get("notif_smtp_port", "587"))
    user = settings.get("notif_smtp_user", "")
    password = settings.get("notif_smtp_pass", "")
    
    if not user or not password or not recipient:
        logger.warning("SMTP not configured")
        return False
        
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = recipient
        
        server = smtplib.SMTP(host, port, timeout=10)
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [recipient], msg.as_string())
        server.quit()
        logger.info(f"Email sent to {recipient}")
        return True
    except Exception as e:
        logger.error(f"SMTP failed: {e}")
        return False

def send_whatsapp_webhook(settings, body):
    webhook_url = settings.get("notif_whatsapp_webhook", "")
    if not webhook_url:
        return False
    try:
        payload = json.dumps({"message": body}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info(f"WhatsApp webhook: {resp.status}")
            return True
    except Exception as e:
        logger.error(f"WhatsApp webhook failed: {e}")
        return False

def send_notification_summary():
    settings = get_notification_settings()
    body = generate_summary_text()
    ok = True
    if settings.get("notif_email_enabled") == "true":
        ok &= send_smtp_email(settings, "NexusTrader Summary", body)
    if settings.get("notif_whatsapp_enabled") == "true":
        ok &= send_whatsapp_webhook(settings, body)
    return ok

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        settings = get_notification_settings()
        body = "Test notification from NexusTrader"
        send_smtp_email(settings, "Test", body)
        send_whatsapp_webhook(settings, body)
        _send_ntfy(settings, "info", "Test", "Test notification")
    else:
        send_notification_summary()


def resolve_alerts_by_category(category: str, title_substring: str = None):
    """Resolve all unresolved alerts matching a category (and optional title substring)."""
    conn = sqlite3.connect(ALERT_DB_PATH)
    if title_substring:
        conn.execute(
            "UPDATE alerts SET resolved = 1 WHERE resolved = 0 AND category = ? AND title LIKE ?",
            (category, f'%{title_substring}%')
        )
    else:
        conn.execute(
            "UPDATE alerts SET resolved = 1 WHERE resolved = 0 AND category = ?",
            (category,)
        )
    conn.commit()
    conn.close()
