#!/usr/bin/env bash
# HUD mail/calendar status provider
# Reads cached data from .omc/state/mail-hud-data.json
# Returns the status_line field for HUD display

CACHE_FILE="${PROJECT_DIR:-.}/.omc/state/mail-hud-data.json"

if [ ! -f "$CACHE_FILE" ]; then
    echo "mail:? | cal:?"
    exit 0
fi

# Check if cache is older than 1 hour
if [ "$(uname)" = "Darwin" ]; then
    AGE=$(( $(date +%s) - $(stat -f %m "$CACHE_FILE") ))
else
    AGE=$(( $(date +%s) - $(stat -c %Y "$CACHE_FILE") ))
fi

if [ "$AGE" -gt 3600 ]; then
    echo "mail:stale | cal:stale"
    exit 0
fi

# Extract status_line from JSON
if command -v python3 &>/dev/null; then
    python3 -c "
import json, sys
try:
    data = json.load(open('$CACHE_FILE'))
    print(data.get('status_line', 'mail:? | cal:?'))
except Exception:
    print('mail:err | cal:err')
"
elif command -v jq &>/dev/null; then
    jq -r '.status_line // "mail:? | cal:?"' "$CACHE_FILE"
else
    echo "mail:? | cal:?"
fi
