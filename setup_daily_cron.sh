#!/bin/bash
# setup_daily_cron.sh
# Sets up a cron job to run the daily agent every day at 12:00 AM.

CRON_CMD="0 0 * * * cd /home/chris/nexustrader && ./daily_agent.sh >> daily_agent.log 2>&1"
TMP_CRON="/tmp/current_crontab"

# Get current crontab (redirecting stderr to avoid no crontab message)
crontab -l > "$TMP_CRON" 2>/dev/null

# Check if command is already scheduled
if grep -q "daily_agent.sh" "$TMP_CRON"; then
    echo "Cron job for daily_agent.sh is already scheduled."
else
    echo "$CRON_CMD" >> "$TMP_CRON"
    crontab "$TMP_CRON"
    echo "Cron job successfully scheduled to run daily at 00:00."
fi

# Clean up
rm -f "$TMP_CRON"
