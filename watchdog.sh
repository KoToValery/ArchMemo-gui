#!/bin/bash
# Watchdog script for ArchiMemo-gui on Linux/Raspberry Pi

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
APP_FILE="$SCRIPT_DIR/app.py"
LOG_FILE="$SCRIPT_DIR/watchdog.log"

echo "Starting watchdog for ArchiMemo-gui..." >> "$LOG_FILE"

while true; do
    echo "[$(date)] Starting app..." >> "$LOG_FILE"
    # Adjust python3 if you use a virtual environment
    python3 "$APP_FILE" >> "$LOG_FILE" 2>&1
    echo "[$(date)] App crashed with exit code $?. Restarting in 5 seconds..." >> "$LOG_FILE"
    sleep 5
done
