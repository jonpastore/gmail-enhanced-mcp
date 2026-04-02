"""AI context tool handlers: thread summarization and reply-needed detection."""

from __future__ import annotations

import re
from typing import Any

from ..calendar.date_parser import DateParser
from ..email_client import EmailClient
from ..triage.engine import JunkDetector
from .search import _extract_body, _get_header

_ACTION_KEYWORDS = re.compile(
    r"\b(please|could you|can you|need you to|action required)\b",
    re.IGNORECASE,
)


def _text_content(text: str) -> dict[str, Any]:
    """Return MCP-format text content."""
    return {"content": [{"type": "text", "text": text}]}


def _error_content(msg: str) -> dict[str, Any]:
    """Return MCP-format error content."""
    return {"content": [{"type": "text", "text": f"Error: {msg}"}], "isError": True}


def _parse_name_email(raw: str) -> tuple[str, str]:
    """Extract display name and email address from a From/To header value.

    Args:
        raw: Raw header value such as "Alice <alice@example.com>".

    Returns:
        Tuple of (name, email).
    """
    m = re.match(r"^(.+?)\s*<([^>]+)>", raw.strip())
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip()
    return "", raw.strip()


def _collect_attachments(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Collect attachment metadata from a message payload.

    Args:
        payload: The message payload dict.

    Returns:
        List of dicts with filename and attachment_id keys.
    """
    attachments: list[dict[str, str]] = []
    for part in payload.get("parts", []):
        if part.get("filename"):
            att_id = part.get("body", {}).get("attachmentId", "")
            attachments.append({"filename": part["filename"], "attachment_id": att_id})
        sub_parts = part.get("parts", [])
        if sub_parts:
            attachments.extend(_collect_attachments({"parts": sub_parts}))
    return attachments


def handle_summarize_thread(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Summarize a Gmail thread with participants, timeline, asks, and deadlines.

    Args:
        args: Tool arguments containing threadId.
        client: Email client for reading thread data.

    Returns:
        MCP content with structured thread summary as JSON.
    """
    import json

    thread_id = args.get("threadId")
    if not thread_id:
        return _error_content("threadId is required")

    try:
        thread = client.read_thread(thread_id)
    except Exception as exc:
        return _error_content(f"Failed to read thread: {exc}")

    messages: list[dict[str, Any]] = thread.get("messages", [])
    my_email = client.email_address.lower()

    participants: dict[str, dict[str, Any]] = {}
    timeline: list[dict[str, Any]] = []
    all_questions: list[str] = []
    all_action_lines: list[str] = []
    all_deadlines: list[str] = []
    all_attachments: list[dict[str, str]] = []

    date_parser = DateParser()

    for msg in messages:
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        from_raw = _get_header(headers, "From")
        to_raw = _get_header(headers, "To")
        cc_raw = _get_header(headers, "CC")
        date_str = _get_header(headers, "Date")

        from_name, from_email = _parse_name_email(from_raw)

        for raw_addr in [from_raw, to_raw, cc_raw]:
            if not raw_addr:
                continue
            for part in raw_addr.split(","):
                part = part.strip()
                if not part:
                    continue
                name, email = _parse_name_email(part)
                key = email.lower()
                if key not in participants:
                    participants[key] = {"email": key, "name": name or key, "message_count": 0}
                if part in (from_raw,):
                    participants[key]["message_count"] += 1

        body = _extract_body(payload)
        body_snippet = body[:200]

        msg_attachments = _collect_attachments(payload)
        all_attachments.extend(msg_attachments)

        timeline.append(
            {
                "from": from_raw,
                "date": date_str,
                "snippet": body_snippet,
                "has_attachments": bool(msg_attachments),
            }
        )

        is_from_me = from_email.lower() == my_email
        if not is_from_me:
            body_scan = body[:10_000]
            for line in body_scan.splitlines():
                if "?" in line and line.strip():
                    all_questions.append(line.strip())
                if _ACTION_KEYWORDS.search(line):
                    all_action_lines.append(line.strip())

            dates = date_parser.extract_dates(body_scan)
            for dm in dates:
                all_deadlines.append(dm.resolved_date.isoformat())

    summary = {
        "thread_id": thread_id,
        "message_count": len(messages),
        "participants": list(participants.values()),
        "timeline": timeline,
        "key_asks": all_action_lines[:10],
        "deadlines": sorted(set(all_deadlines)),
        "open_questions": all_questions[:10],
        "attachments": all_attachments,
    }

    return _text_content(json.dumps(summary, indent=2))


def _qualifies_for_reply(
    msg: dict[str, Any],
    thread: dict[str, Any],
    my_email: str,
    junk_detector: JunkDetector,
) -> tuple[bool, list[str]]:
    """Check whether a message qualifies as needing a reply.

    Args:
        msg: The Gmail message dict.
        thread: The full thread dict for the message.
        my_email: The authenticated user's email address.
        junk_detector: JunkDetector instance for junk classification.

    Returns:
        Tuple of (qualifies, reasons).
    """
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    to_raw = _get_header(headers, "To").lower()
    body = _extract_body(payload)[:10_000]

    reasons: list[str] = []

    if my_email in to_raw:
        reasons.append("You are in To:")

    thread_messages = thread.get("messages", [])
    if thread_messages:
        last_msg = thread_messages[-1]
        last_payload = last_msg.get("payload", {})
        last_headers = last_payload.get("headers", [])
        last_from = _get_header(last_headers, "From").lower()
        if my_email not in last_from:
            reasons.append("Last message not from you")

    if "?" in body:
        reasons.append("Contains question")

    if _ACTION_KEYWORDS.search(body):
        reasons.append("Contains action request")

    junk = junk_detector.analyze(msg)
    if not junk.is_junk:
        reasons.append("Not junk")

    return len(reasons) >= 2, reasons


def handle_needs_reply(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Find inbox messages that likely need a reply from the user.

    Args:
        args: Tool arguments with optional maxResults and daysBack.
        client: Email client for searching and reading messages.

    Returns:
        MCP content with list of messages needing reply, sorted by date desc.
    """
    import json
    from datetime import date, timedelta

    max_results: int = args.get("maxResults", 20)
    days_back: int = args.get("daysBack", 7)

    cutoff = date.today() - timedelta(days=days_back)
    after_str = cutoff.strftime("%Y/%m/%d")
    query = f"is:inbox is:unread after:{after_str}"

    try:
        result = client.search_messages(q=query, max_results=max_results)
    except Exception as exc:
        return _error_content(f"Search failed: {exc}")

    stubs: list[dict[str, Any]] = result.get("messages", [])
    if not stubs:
        return _text_content("No unread inbox messages found in the specified window.")

    my_email = client.email_address.lower()
    junk_detector = JunkDetector()
    qualifying: list[dict[str, Any]] = []

    for stub in stubs:
        try:
            msg = client.read_message(stub["id"])
            thread = client.read_thread(stub.get("threadId", stub["id"]))
        except Exception:
            continue

        qualifies, reasons = _qualifies_for_reply(msg, thread, my_email, junk_detector)
        if not qualifies:
            continue

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        qualifying.append(
            {
                "message_id": msg["id"],
                "thread_id": msg.get("threadId", ""),
                "from": _get_header(headers, "From"),
                "subject": _get_header(headers, "Subject"),
                "date": _get_header(headers, "Date"),
                "reason": "; ".join(reasons),
            }
        )

    qualifying.sort(key=lambda x: x["date"], reverse=True)
    return _text_content(
        json.dumps({"needs_reply": qualifying, "count": len(qualifying)}, indent=2)
    )
