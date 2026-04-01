"""Email hygiene tool handlers: trash, block, spam, contacts, unsubscribe."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from ..email_client import EmailClient
from ..triage.cache import TriageCache
from ..triage.models import SenderTier
from ..triage.priority_senders import PrioritySenderManager


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _gmail_only(client: EmailClient) -> dict[str, Any] | None:
    if client.provider != "gmail":
        return _text_content("This tool is only available for Gmail accounts.")
    return None


def handle_trash_messages(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Trash messages by IDs or search query."""
    guard = _gmail_only(client)
    if guard:
        return guard

    message_ids = args.get("messageIds")
    query = args.get("query")

    if not message_ids and not query:
        return _text_content("Provide messageIds or query to identify messages to trash.")

    if message_ids:
        result = client.trash_messages(message_ids)  # type: ignore[attr-defined]
    else:
        max_results = args.get("maxResults", 500)
        result = client.trash_by_query(query, max_results)  # type: ignore[attr-defined]

    count = result["trashed_count"]
    ids_preview = json.dumps(result["message_ids"][:20])
    text = f"Trashed {count} messages.\nMessage IDs: {ids_preview}"
    if count > 20:
        text += f"\n... and {count - 20} more"
    return _text_content(text)


def handle_block_sender(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Block a sender: create auto-delete filter + trash existing."""
    guard = _gmail_only(client)
    if guard:
        return guard

    sender = args.get("sender")
    if not sender:
        return _text_content("sender is required.")

    result = client.create_block_filter(sender)  # type: ignore[attr-defined]
    return _text_content(
        f"Blocked {sender}.\n"
        f"Filter ID: {result['filter_id']}\n"
        f"Existing messages trashed: {result['existing_trashed']}"
    )


def handle_report_spam(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Report messages as spam."""
    guard = _gmail_only(client)
    if guard:
        return guard

    message_ids = args.get("messageIds")
    if not message_ids:
        return _text_content("messageIds is required.")

    result = client.report_spam(message_ids)  # type: ignore[attr-defined]
    return _text_content(f"Reported {result['reported_count']} messages as spam.")


def handle_list_contacts(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """List Google contacts with email addresses."""
    guard = _gmail_only(client)
    if guard:
        return guard

    max_results = args.get("maxResults", 2000)
    contacts = client.get_contacts(max_results)  # type: ignore[attr-defined]
    if not contacts:
        return _text_content("No contacts with email addresses found.")

    lines = [f"Found {len(contacts)} contacts with email addresses:\n"]
    for c in contacts:
        emails = ", ".join(c["emails"])
        lines.append(f"  {c['name']} <{emails}>")
    return _text_content("\n".join(lines))


def handle_import_contacts_as_priority(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Import Google contacts as priority senders."""
    guard = _gmail_only(client)
    if guard:
        return guard

    tier_str = args.get("tier", "normal")
    try:
        tier = SenderTier(tier_str)
    except ValueError:
        return _text_content(f"Invalid tier: {tier_str}. Use critical, high, or normal.")

    contacts = client.get_contacts()  # type: ignore[attr-defined]
    if not contacts:
        return _text_content("No contacts with email addresses found.")

    mgr = PrioritySenderManager(cache)
    added = 0
    skipped = 0
    for contact in contacts:
        for email in contact["emails"]:
            if mgr.match(email):
                skipped += 1
            else:
                label = contact["name"]
                mgr.add(email, tier, label)
                added += 1

    return _text_content(
        f"Imported contacts as priority senders (tier={tier_str}).\n"
        f"Added: {added}\n"
        f"Skipped (already matched): {skipped}\n"
        f"Total contacts processed: {len(contacts)}"
    )


def handle_get_unsubscribe_link(
    args: dict[str, Any], client: EmailClient
) -> dict[str, Any]:
    """Extract unsubscribe link from a message."""
    guard = _gmail_only(client)
    if guard:
        return guard

    message_id = args.get("messageId")
    if not message_id:
        return _text_content("messageId is required.")

    result = client.extract_unsubscribe_link(message_id)  # type: ignore[attr-defined]
    if not result["found"]:
        return _text_content("No unsubscribe link found in this message.")

    lines = ["Unsubscribe options found:"]
    if result["unsubscribe_url"]:
        lines.append(f"  URL: {result['unsubscribe_url']}")
    if result["unsubscribe_mailto"]:
        lines.append(f"  Email: {result['unsubscribe_mailto']}")
    return _text_content("\n".join(lines))
