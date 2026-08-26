"""Unsubscribe from a mailing list after an explicit tool call."""

from __future__ import annotations

import re
from typing import Any

from ..handler_context import HandlerContext
from ..sort.models import MailRule, MailRuleMatch
from ..sort.unsub import execute_one_click, parse_mailto
from .response import error_content as _error_content
from .response import text_content as _text_content

_FROM_EMAIL = re.compile(r"<([^>]+)>")


def _sender_address(from_header: str) -> str | None:
    match = _FROM_EMAIL.search(from_header)
    if match:
        return match.group(1).strip()
    if "@" in from_header:
        return from_header.strip()
    return None


def handle_unsubscribe(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """Execute List-Unsubscribe for a message; optionally add a Junk sort rule.

    Prefers RFC 8058 one-click HTTPS POST. Falls back to mailto send (this
    tool call is the send approval). Refuses a non-one-click HTTP GET.

    Args:
        args: messageId required; createJunkRule optional bool.
        ctx: Handler context with EmailClient.

    Returns:
        MCP text describing the method used, or an error.
    """
    message_id = args.get("messageId")
    if not message_id:
        return _error_content("messageId is required.")
    try:
        info = ctx.client.extract_unsubscribe_link(str(message_id))
    except Exception as exc:
        return _error_content(str(exc))
    if not info.get("found"):
        return _error_content("No unsubscribe link found in this message.")

    try:
        method = _perform_unsubscribe(info, ctx)
    except (ValueError, RuntimeError) as exc:
        return _error_content(str(exc))

    extra = ""
    if args.get("createJunkRule"):
        extra = _maybe_junk_rule(str(message_id), ctx)
    return _text_content(f"Unsubscribed via {method}.{extra}")


def _perform_unsubscribe(info: dict[str, Any], ctx: HandlerContext) -> str:
    url = info.get("unsubscribe_url")
    mailto = info.get("unsubscribe_mailto")
    if url and info.get("one_click"):
        execute_one_click(str(url))
        return "one-click POST"
    if mailto:
        to_addr, subject = parse_mailto(str(mailto))
        ctx.client.send_email(to=to_addr, subject=subject, body="unsubscribe")
        return "mailto"
    if url:
        raise RuntimeError(
            "Unsubscribe URL is not one-click. Open it in a browser; refusing to GET it."
        )
    raise RuntimeError("No unsubscribe link found in this message.")


def _maybe_junk_rule(message_id: str, ctx: HandlerContext) -> str:
    msg = ctx.client.read_message(message_id)
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in msg.get("payload", {}).get("headers", [])
    }
    sender = _sender_address(headers.get("from", ""))
    if not sender:
        return "\nJunk rule skipped: could not parse sender."
    try:
        rule = MailRule(
            name=f"Junk {sender}",
            match=MailRuleMatch(from_value=sender),
            destination="Junk",
        )
        created = ctx.client.create_sort_rule(rule, apply_existing=True)
    except Exception as exc:
        return f"\nJunk rule failed: {exc}"
    return f"\nCreated Junk rule {created.id}."
