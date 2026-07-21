"""Proton Mail Bridge client for NexusTrader notifications.

Uses Proton Mail Bridge (https://proton.me/mail/bridge) running on chris-System.
The bridge exposes SMTP on 127.0.0.1:1025 by default and handles IMAP/POP too.

Credentials:
- Proton user: Kevin_the_minion_the_nineteenth
- Bridge runs locally on chris-System (192.168.0.77)
"""
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, formataddr

logger = logging.getLogger(__name__)

# Proton Mail Bridge defaults
BRIDGE_HOST = "192.168.0.77"
BRIDGE_PORT = 10250  # Proton Bridge SMTP (socat forward from 127.0.0.1:1025)
BRIDGE_USER = "Kevin_the_minion_the_nineteenth@proton.me"
BRIDGE_FROM_NAME = "NexusTrader"
BRIDGE_FROM_ADDR = "Kevin_the_minion_the_nineteenth@proton.me"

# No STARTTLS needed for Bridge — it's a local proxy that handles encryption upstream
# Bridge uses PLAIN auth on loopback by default


def send_notification(
    recipient,
    subject,
    body,
    html_body=None,
    bridge_host=None,
    bridge_port=None,
    bridge_user=None,
    bridge_pass=None,
):
    """Send an email notification via Proton Mail Bridge.

    NOTE: Proton Mail Bridge requires a PAID Proton plan (Mail Plus or higher).
    If the bridge returns auth errors, upgrade at https://account.proton.me/upgrade

    Args:
        recipient: Email recipient address
        subject: Email subject line
        body: Plain-text email body
        html_body: Optional HTML version of the body
        bridge_host: Proton Bridge host (default: 192.168.0.77)
        bridge_port: SMTP port (default: 10250 = socat forward from bridge's 127.0.0.1:1025)
        bridge_user: Bridge username (default: Proton email)
        bridge_pass: Bridge password (DB-stored, auto-loaded)

    Returns:
        (ok: bool, message: str)
    """
    host = bridge_host or BRIDGE_HOST
    port = bridge_port or BRIDGE_PORT
    user = bridge_user or BRIDGE_USER

    if bridge_pass is None:
        try:
            import sqlite3 as _sqlite3
            import os as _os
            db = _sqlite3.connect(_os.path.expanduser("~/.nexustrader/nexustrader.db"))
            row = db.execute("SELECT value FROM settings WHERE key='proton_bridge_password'").fetchone()
            db.close()
            bridge_pass = row[0] if row else ""
        except Exception:
            bridge_pass = ""

    if not bridge_pass:
        logger.error("[ProtonBridge] No bridge password configured")
        return False, "No Proton Bridge password configured"

    if not recipient:
        logger.error("[ProtonBridge] No recipient configured")
        return False, "No recipient email configured"

    # Check if email notifications are enabled
    try:
        import sqlite3 as _sqlite3
        import os as _os
        db = _sqlite3.connect(_os.path.expanduser("~/.nexustrader/nexustrader.db"))
        row = db.execute("SELECT value FROM settings WHERE key='notif_email_enabled'").fetchone()
        db.close()
        enabled = row and row[0] and row[0].lower() == "true"
        if not enabled:
            logger.info("[ProtonBridge] Email notifications disabled — skipping send")
            return False, "Email notifications disabled"
    except Exception:
        pass

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((BRIDGE_FROM_NAME, BRIDGE_FROM_ADDR))
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["X-Mailer"] = "NexusTrader ProtonBridge v1.0"

    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.login(user, bridge_pass)
            smtp.send_message(msg)
        logger.info(f"[ProtonBridge] Email sent to {recipient}: {subject}")
        return True, f"Sent to {recipient}"
    except smtplib.SMTPAuthenticationError as e:
        err_msg = str(e)
        if "10004" in err_msg or "upgrade" in err_msg.lower():
            logger.error(f"[ProtonBridge] Auth failed — Proton Mail Bridge requires a PAID plan: {e}")
            return False, "Proton Bridge requires a paid plan (Mail Plus or higher). Upgrade at https://account.proton.me/upgrade"
        logger.error(f"[ProtonBridge] Auth failed: {e}")
        return False, f"Authentication failed: {e}"
    except smtplib.SMTPConnectError as e:
        logger.error(f"[ProtonBridge] Connection failed to {host}:{port}: {e}")
        return False, f"Cannot reach Proton Bridge at {host}:{port}. Is protonmail-bridge running on chris-System?"
    except Exception as e:
        logger.error(f"[ProtonBridge] Send failed: {e}")
        return False, str(e)


def send_trade_notification(trade_data):
    """Send a formatted trade notification email.

    Args:
        trade_data: dict with keys: symbol, direction, entry_price, exit_price,
                    pnl, pnl_pct, duration_seconds, reason
    """
    symbol = trade_data.get("symbol", "???")
    direction = trade_data.get("direction", "unknown").upper()
    entry = trade_data.get("entry_price", 0)
    exit_p = trade_data.get("exit_price", 0)
    pnl = trade_data.get("pnl", 0)
    pnl_pct = trade_data.get("pnl_pct", 0)
    dur = trade_data.get("duration_seconds", 0)
    reason = trade_data.get("reason", "unknown")

    emoji = "📈" if direction == "BUY" else "📉"
    win = "✅ WIN" if pnl > 0 else "❌ LOSS"

    subject = f"{win} {symbol} {direction} — ${pnl:+.2f} ({pnl_pct:+.2f}%)"

    body = f"""NexusTrader Trade Closed

{emoji} {symbol} {direction}
Entry: ${entry:.6f}
Exit:  ${exit_p:.6f}
P&L:   ${pnl:+.2f} ({pnl_pct:+.2f}%)
Duration: {dur:.0f}s ({dur/60:.1f}m)
Reason: {reason}

---
NexusTrader AI Neuro-Quantitative Suite
"""
    html = f"""<html><body style="font-family:sans-serif">
<h2>{win}</h2>
<table cellpadding="4" style="border-collapse:collapse">
<tr><td><b>Symbol</b></td><td>{emoji} {symbol}</td></tr>
<tr><td><b>Direction</b></td><td>{direction}</td></tr>
<tr><td><b>Entry</b></td><td>${entry:.6f}</td></tr>
<tr><td><b>Exit</b></td><td>${exit_p:.6f}</td></tr>
<tr><td><b>P&amp;L</b></td><td style="color:{'green' if pnl > 0 else 'red'}">${pnl:+.2f} ({pnl_pct:+.2f}%)</td></tr>
<tr><td><b>Duration</b></td><td>{dur:.0f}s ({dur/60:.1f}m)</td></tr>
<tr><td><b>Reason</b></td><td>{reason}</td></tr>
</table>
<hr><small>NexusTrader AI Neuro-Quantitative Suite</small>
</body></html>"""

    import sqlite3 as _sqlite3
    import os as _os
    try:
        db = _sqlite3.connect(_os.path.expanduser("~/.nexustrader/nexustrader.db"))
        row = db.execute("SELECT value FROM settings WHERE key='notif_email_recipient'").fetchone()
        db.close()
        recipient = row[0] if row and row[0] else "churchill.c.j@gmail.com"
    except Exception:
        recipient = "churchill.c.j@gmail.com"

    return send_notification(recipient, subject, body, html_body=html)


def send_alert_notification(alert_type, message, severity="WARNING"):
    """Send an alert notification (kill switch, risk threshold, etc.)."""
    severity_emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵", "SUCCESS": "🟢"}
    emoji = severity_emoji.get(severity, "📢")

    subject = f"{emoji} [{severity}] NexusTrader Alert: {alert_type}"

    body = f"""NexusTrader Alert

Type:     {alert_type}
Severity: {severity}
Message:  {message}

---
NexusTrader AI Neuro-Quantitative Suite
"""

    recipient = "churchill.c.j@gmail.com"  # default
    try:
        import sqlite3 as _sqlite3
        import os as _os
        db = _sqlite3.connect(_os.path.expanduser("~/.nexustrader/nexustrader.db"))
        row = db.execute("SELECT value FROM settings WHERE key='notif_email_recipient'").fetchone()
        db.close()
        if row and row[0]:
            recipient = row[0]
    except Exception:
        pass

    return send_notification(recipient, subject, body)


def send_daily_summary(summary_data):
    """Send end-of-day trading summary.

    Args:
        summary_data: dict with: date, balance, equity, total_pnl, pnl_pct,
                      trade_count, win_count, loss_count, win_rate, open_positions
    """
    date = summary_data.get("date", "Today")
    balance = summary_data.get("balance", 0)
    equity = summary_data.get("equity", 0)
    total_pnl = summary_data.get("total_pnl", 0)
    pnl_pct = summary_data.get("pnl_pct", 0)
    trades = summary_data.get("trade_count", 0)
    wins = summary_data.get("win_count", 0)
    losses = summary_data.get("loss_count", 0)
    win_rate = summary_data.get("win_rate", 0)
    open_pos = summary_data.get("open_positions", 0)

    subject = f"📊 NexusTrader Daily Summary — {date} — ${total_pnl:+.2f}"

    body = f"""NexusTrader Daily Summary — {date}

Portfolio:
  Balance: ${balance:.2f}
  Equity:  ${equity:.2f}
  P&L:     ${total_pnl:+.2f} ({pnl_pct:+.2f}%)

Trading:
  Trades:  {trades}
  Wins:    {wins} / Losses: {losses}
  Win Rate: {win_rate:.1f}%
  Open Positions: {open_pos}

---
NexusTrader AI Neuro-Quantitative Suite
"""

    recipient = "churchill.c.j@gmail.com"
    try:
        import sqlite3 as _sqlite3
        import os as _os
        db = _sqlite3.connect(_os.path.expanduser("~/.nexustrader/nexustrader.db"))
        row = db.execute("SELECT value FROM settings WHERE key='notif_email_recipient'").fetchone()
        db.close()
        if row and row[0]:
            recipient = row[0]
    except Exception:
        pass

    return send_notification(recipient, subject, body)
