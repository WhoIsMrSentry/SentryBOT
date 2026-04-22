#!/bin/bash

# SentryBOT Remote TTS Server Watchdog / Cronjob
# This script can be added to crontab to ensure the TTS server is always running.
#
# To add to crontab, run: crontab -e
# Then add the following line to run this check every 5 minutes:
# */5 * * * * /path/to/SentryBOT/tools/remote_tts_server/cronjob.sh >> /var/log/sentrybot_tts_cron.log 2>&1

PORT=5000
HOST="http://localhost:$PORT"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if the /healthz endpoint is responsive
if curl -s -f "$HOST/healthz" > /dev/null; then
    echo "$(date): TTS Server is running and healthy."
else
    echo "$(date): TTS Server is down! Attempting to restart..."
    
    # Example for native restart:
    # cd "$APP_DIR" && nohup python app.py > server.log 2>&1 &
    
    # Example for Docker restart (uncomment if using Docker):
    # docker restart sentrybot-tts-server || docker run -d --name sentrybot-tts-server -p 5000:5000 -v $APP_DIR/runtime:/app/runtime sentrybot-tts:latest
    
    # Fallback default: start using Python natively in the background if no container is defined
    cd "$APP_DIR" || exit 1
    
    # Ensure virtual environment is activated if you have one
    # source ../../.venv/bin/activate
    
    nohup python app.py >> "$APP_DIR/cron_restart.log" 2>&1 &
    echo "$(date): Restart command issued."
fi
