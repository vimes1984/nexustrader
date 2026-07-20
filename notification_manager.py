# notification_manager.py
import sqlite3
import json
import smtplib
from email.mime.text import MIMEText
import urllib.request
import urllib.error
import logging
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NotificationManager")

def get_notification_settings():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    
    settings = {
        "notif_email_enabled": "false",
        "notif_email_recipient": "churchill.c.j@gmail.com",
        "notif_smtp_host": "smtp.gmail.com",
        "notif_smtp_port": "587",
        "notif_smtp_user": "",
        "notif_smtp_pass": "",
        "notif_whatsapp_enabled": "false",
        "notif_whatsapp_webhook": ""
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

def generate_summary_text():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Load balances from settings
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('portfolio_balance', 'portfolio_live_equity', 'initial_portfolio_balance', 'daily_income_goal')")
    settings = {r[0]: r[1] for r in cursor.fetchall()}
    
    # Get trade statistics
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
    recipient = settings.get("notif_email_recipient", "churchill.c.j@gmail.com")
    host = settings.get("notif_smtp_host", "smtp.gmail.com")
    port = int(settings.get("notif_smtp_port", "587"))
    user = settings.get("notif_smtp_user", "")
    password = settings.get("notif_smtp_pass", "")
    
    if not user or not password:
        logger.warning("SMTP user credentials are not configured. Logging summary fallback.")
        logger.info(f"Fallback Email Body:\n{body}")
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
        logger.info(f"Summary email successfully sent to {recipient}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {e}")
        return False

def send_whatsapp_webhook(settings, body):
    webhook_url = settings.get("notif_whatsapp_webhook", "")
    if not webhook_url:
        logger.warning("WhatsApp openclaw webhook URL is not configured.")
        return False
        
    try:
        payload = json.dumps({
            "recipient": settings.get("notif_email_recipient", "churchill.c.j@gmail.com"),
            "message": body
        }).encode("utf-8")
        
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read().decode("utf-8")
            logger.info(f"WhatsApp webhook response: {res_data}")
            return True
    except Exception as e:
        logger.error(f"Failed to trigger WhatsApp openclaw webhook: {e}")
        return False

def send_notification_summary():
    settings = get_notification_settings()
    body = generate_summary_text()
    
    success = True
    if settings.get("notif_email_enabled") == "true":
        logger.info("Sending scheduled daily summary email...")
        email_ok = send_smtp_email(settings, "NexusTrader - Daily Quant Summary", body)
        if not email_ok:
            success = False
            
    if settings.get("notif_whatsapp_enabled") == "true":
        logger.info("Triggering scheduled daily WhatsApp webhook...")
        wa_ok = send_whatsapp_webhook(settings, body)
        if not wa_ok:
            success = False
            
    return success

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("Sending test notification...")
        settings = get_notification_settings()
        body = "⚠️ NexusTrader Connection & Notification Test\n\nThis is a manual test verification message to confirm notification routing is operational."
        send_smtp_email(settings, "NexusTrader - Notification Test", body)
        send_whatsapp_webhook(settings, body)
    else:
        send_notification_summary()
