#!/usr/bin/env bash
# deploy.sh - NexusTrader Automated Deployment Script
# Deploys code from laptop to the Proxmox LXC container nexustrader.local.

set -e

REMOTE_HOST="192.168.0.144"
REMOTE_USER="root"
REMOTE_PATH="/root/nexustrader"

# 0. Run Unit Tests locally
echo "🧪 Running unit tests..."
if ! python3 -m unittest discover -s tests/; then
    echo "❌ Error: Unit tests failed. Aborting deployment!"
    exit 1
fi
echo "✅ All unit tests passed!"

# 1. Verify connection
if ! ping -c 1 -W 2 "$REMOTE_HOST" > /dev/null 2>&1; then
    echo "❌ Error: Remote host $REMOTE_HOST is not reachable on the LAN."
    exit 1
fi

# 2. Sync codebase
echo "📦 Syncing code files via rsync..."
rsync -av -e "ssh -o StrictHostKeyChecking=no" \
    --exclude=".git" \
    --exclude="venv" \
    --exclude="__pycache__" \
    --exclude="*.db" \
    --exclude="*.log" \
    --exclude="nexustrader_log.txt" \
    ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

# 3. Reload and restart daemon
echo "⚙️ Reloading systemd and restarting daemon..."
ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "systemctl daemon-reload && systemctl restart nexustrader.service"

# 3.5. Ensure automated daily backup cron job is registered
echo "⏰ Configuring automated daily backup scheduler (3:00 AM)..."
ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "
  TMP_CRON=\$(mktemp)
  crontab -l > \$TMP_CRON 2>/dev/null || true
  if ! grep -q 'backup_manager.py' \$TMP_CRON; then
    echo '0 3 * * * cd /root/nexustrader && /root/nexustrader/venv/bin/python3 backup_manager.py backup >> /root/.nexustrader/backup_log.txt 2>&1' >> \$TMP_CRON
    crontab \$TMP_CRON
    echo 'Scheduled daily backup cron job successfully.'
  fi
  rm -f \$TMP_CRON
"

# 3.7. Ensure automated twice-daily notification cron job is registered
echo "⏰ Configuring twice-daily notification summary scheduler (9:00 AM & 9:00 PM)..."
ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "
  TMP_CRON=\$(mktemp)
  crontab -l > \$TMP_CRON 2>/dev/null || true
  if ! grep -q 'notification_manager.py' \$TMP_CRON; then
    echo '0 9,21 * * * cd /root/nexustrader && /root/nexustrader/venv/bin/python3 notification_manager.py >> /root/.nexustrader/notification_log.txt 2>&1' >> \$TMP_CRON
    crontab \$TMP_CRON
    echo 'Scheduled twice-daily notification summary cron job successfully.'
  fi
  rm -f \$TMP_CRON
"

# 3.9. Ensure automated monthly quant strategy researcher cron job is registered
echo "⏰ Configuring automated monthly quant strategy researcher (1st of month at 4:00 AM)..."
ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "
  TMP_CRON=\$(mktemp)
  crontab -l > \$TMP_CRON 2>/dev/null || true
  if ! grep -q 'monthly_researcher.py' \$TMP_CRON; then
    echo '0 4 1 * * cd /root/nexustrader && /root/nexustrader/venv/bin/python3 monthly_researcher.py >> /root/.nexustrader/monthly_research_log.txt 2>&1' >> \$TMP_CRON
    crontab \$TMP_CRON
    echo 'Scheduled monthly quant strategy researcher cron job successfully.'
  fi
  rm -f \$TMP_CRON
"

# 4. Print status
echo "🔍 Verifying active daemon status..."
sleep 2
ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "systemctl status nexustrader.service"

echo "=========================================================="
echo "🎉 Deployment Completed Successfully!"
echo "=========================================================="
