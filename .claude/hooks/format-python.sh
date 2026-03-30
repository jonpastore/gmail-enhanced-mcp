#!/bin/bash
# PostToolUse hook: auto-format Python files after Edit/Write
# Matches: Edit|Write on .py files

CHANGED_FILE="${CLAUDE_FILE_PATH:-}"

if [[ -z "$CHANGED_FILE" ]] || [[ "$CHANGED_FILE" != *.py ]]; then
    exit 0
fi

if [[ ! -f "$CHANGED_FILE" ]]; then
    exit 0
fi

cd /home/jon/projects/gmail-enhanced-mcp || exit 0

python -m ruff format "$CHANGED_FILE" 2>/dev/null
python -m ruff check --fix "$CHANGED_FILE" 2>/dev/null

exit 0
