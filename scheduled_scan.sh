#!/bin/bash
# Scheduled scan trigger script for Linux/Raspberry Pi

APP_URL="http://localhost:5000/run_full"

echo "[$(date)] Triggering scheduled full scan..."
curl -X POST "$APP_URL"
echo ""
echo "[$(date)] Done."
