#!/usr/bin/env python3
"""Refresh mail HUD cache for statusline display.

Runs standalone (no MCP server needed). Directly uses Google/Microsoft
APIs with existing tokens to fetch unread counts. No src/ imports needed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def get_gmail_unread(email: str) -> int:
    """Get unread important count for a Gmail account."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = PROJECT_DIR / "credentials" / email / "token.json"
    if not token_path.exists():
        return 0

    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())

    svc = build("gmail", "v1", credentials=creds)
    result = svc.users().messages().list(
        userId="me", q="is:unread is:important", maxResults=1
    ).execute()
    return result.get("resultSizeEstimate", len(result.get("messages", [])))


def get_outlook_unread(email: str, client_id: str, tenant_id: str) -> int:
    """Get unread important count for an Outlook account."""
    import requests as req

    token_path = PROJECT_DIR / "credentials" / email / "token.json"
    if not token_path.exists():
        return 0

    token_data = json.loads(token_path.read_text())
    access_token = token_data.get("access_token", "")
    if not access_token:
        return 0

    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://graph.microsoft.com/v1.0/me/messages?$filter=isRead eq false and importance eq 'high'&$count=true&$top=1"
    resp = req.get(url, headers=headers, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("@odata.count", len(resp.json().get("value", [])))
    return 0


def main() -> None:
    accounts_path = PROJECT_DIR / "accounts.json"
    if not accounts_path.exists():
        return

    accounts_data = json.loads(accounts_path.read_text())
    accounts = accounts_data.get("accounts", [])

    results = []
    total_unread = 0

    for acc in accounts:
        email = acc["email"]
        provider = acc.get("provider", "gmail")
        unread = 0

        try:
            if provider == "gmail":
                unread = get_gmail_unread(email)
            elif provider == "outlook":
                azure = acc.get("azure", {})
                unread = get_outlook_unread(
                    email, azure.get("client_id", ""), azure.get("tenant_id", "")
                )
        except Exception:
            pass

        results.append({"email": email, "provider": provider, "unread_priority": unread})
        total_unread += unread

    acct_count = len(results)
    status_line = f"mail:{acct_count}acct unread:{total_unread} | cal:clear"

    state_dir = PROJECT_DIR / ".omc" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "accounts": results,
        "calendar": [],
        "status_line": status_line,
    }
    (state_dir / "mail-hud-data.json").write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
