#!/bin/bash
# PreToolUse hook: block edits to credential files
# Matches: Edit|Write on credentials/ or .env

CHANGED_FILE="${CLAUDE_FILE_PATH:-}"

if [[ -z "$CHANGED_FILE" ]]; then
    exit 0
fi

if [[ "$CHANGED_FILE" == */credentials/* ]] || [[ "$CHANGED_FILE" == */.env ]]; then
    echo "BLOCKED: Direct edits to credential files are not allowed."
    echo "Use 'python -m gmail_mcp auth' to manage credentials."
    exit 1
fi

exit 0
