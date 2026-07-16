#!/bin/bash
# setup_weekly_cron.sh
# Sets up a cron job to run the weekly blog agent every Sunday at 11:59 PM.

CRON_CMD="59 23 * * 0 cd /home/chris/nexustrader && /usr/bin/python3 blog_agent.py >> blog_agent.log 2>&1"
TMP_CRON="/tmp/current_crontab"

# Get current crontab (redirecting stderr to avoid no crontab message)
crontab -l > "$TMP_CRON" 2>/dev/null

# Check if command is already scheduled
if grep -q "blog_agent.py" "$TMP_CRON"; then
    echo "Cron job for blog_agent.py is already scheduled."
else
    echo "$CRON_CMD" >> "$TMP_CRON"
    crontab "$TMP_CRON"
    echo "Cron job successfully scheduled to run weekly (Sundays at 23:59)."
fi

# Clean up
rm -f "$TMP_CRON"
