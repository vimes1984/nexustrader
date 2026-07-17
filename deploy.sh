#!/usr/bin/env bash
# deploy.sh - NexusTrader Automated Deployment Script
# Deploys code from laptop to the Proxmox LXC container nexustrader.local.

set -e

REMOTE_HOST="nexustrader.local"
REMOTE_USER="root"
REMOTE_PATH="/root/nexustrader"

echo "=========================================================="
echo "🚀 Deploying NexusTrader to Proxmox ($REMOTE_HOST)..."
echo "=========================================================="

# 1. Verify connection
if ! ping -c 1 -W 2 "$REMOTE_HOST" > /dev/null 2>&1; then
    echo "❌ Error: Remote host $REMOTE_HOST is not reachable on the LAN."
    exit 1
fi

# 2. Sync codebase
echo "📦 Syncing code files via rsync..."
rsync -av \
    --exclude=".git" \
    --exclude="venv" \
    --exclude="__pycache__" \
    --exclude="*.db" \
    --exclude="*.log" \
    --exclude="nexustrader_log.txt" \
    ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

# 3. Reload and restart daemon
echo "⚙️ Reloading systemd and restarting daemon..."
ssh "$REMOTE_USER@$REMOTE_HOST" "systemctl daemon-reload && systemctl restart nexustrader.service"

# 4. Print status
echo "🔍 Verifying active daemon status..."
sleep 2
ssh "$REMOTE_USER@$REMOTE_HOST" "systemctl status nexustrader.service"

echo "=========================================================="
echo "🎉 Deployment Completed Successfully!"
echo "=========================================================="
