#!/usr/bin/env python3
"""Generate and send email digest. Runs standalone via cron."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and send email digest")
    parser.add_argument("--account", required=True, help="Account email address")
    parser.add_argument(
        "--period",
        default=os.getenv("DIGEST_FREQUENCY", "daily"),
        choices=["daily", "weekly"],
        help="Digest period",
    )
    args = parser.parse_args()

    accounts_path = PROJECT_DIR / "accounts.json"
    if not accounts_path.exists():
        print(f"ERROR: accounts.json not found at {accounts_path}", file=sys.stderr)
        sys.exit(1)

    accounts_data = json.loads(accounts_path.read_text())
    accounts = accounts_data.get("accounts", [])
    account_cfg = next((a for a in accounts if a["email"] == args.account), None)
    if account_cfg is None:
        print(f"ERROR: account {args.account!r} not found in accounts.json", file=sys.stderr)
        sys.exit(1)

    provider = account_cfg.get("provider", "gmail")
    client = None
    cache = None
    calendar_ctx = None

    from src.triage.cache import TriageCache

    cache_db = PROJECT_DIR / "data" / "triage_cache.db"
    cache = TriageCache(cache_db)
    cache.initialize()

    if provider == "gmail":
        from src.auth import TokenManager
        from src.gmail_client import GmailClient

        token_mgr = TokenManager(str(PROJECT_DIR / "credentials" / args.account))
        creds = token_mgr.get_credentials()
        client = GmailClient(creds)
    elif provider == "outlook":
        from src.microsoft_auth import MicrosoftTokenManager
        from src.outlook_client import OutlookClient

        azure = account_cfg.get("azure", {})
        token_mgr = MicrosoftTokenManager(
            client_id=azure.get("client_id", ""),
            tenant_id=azure.get("tenant_id", ""),
            token_path=str(PROJECT_DIR / "credentials" / args.account / "token.json"),
        )
        access_token = token_mgr.get_access_token()
        client = OutlookClient(access_token)
    else:
        print(f"ERROR: unsupported provider {provider!r}", file=sys.stderr)
        sys.exit(1)

    if os.getenv("CALENDAR_ENABLED", "false").lower() == "true":
        try:
            from src.calendar.context import CalendarContext

            calendar_ctx = CalendarContext.from_credentials(
                str(PROJECT_DIR / "credentials" / args.account)
            )
        except Exception as exc:
            print(f"WARNING: calendar unavailable: {exc}", file=sys.stderr)

    from src.digest.engine import DigestEngine
    from src.digest.formatter import format_digest_html

    engine = DigestEngine(client, cache, calendar_ctx)
    result = engine.generate(period=args.period, max_results=100)

    html = format_digest_html(result)
    date_str = datetime.now(UTC).strftime("%b %d, %Y")
    subject = f"[Digest] {args.period.title()} Email Summary \u2014 {date_str}"

    try:
        client.send_email(
            to=args.account,
            subject=subject,
            body=html,
            content_type="text/html",
        )
        result.sent = True
        print(f"Digest sent to {args.account}")
    except Exception as exc:
        print(f"WARNING: send failed: {exc}", file=sys.stderr)

    state_dir = PROJECT_DIR / ".omc" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    account_hash = args.account.replace("@", "_").replace(".", "_")
    fallback_path = state_dir / f"last-digest-{account_hash}.json"
    fallback_path.write_text(result.model_dump_json(indent=2))
    print(f"Digest written to {fallback_path}")

    summary = result.summary
    print(
        f"Summary: {summary.total_unread} unread | "
        f"top items: {len(summary.top_items)} | "
        f"sent: {result.sent}"
    )

    cache.close()


if __name__ == "__main__":
    main()
