from __future__ import annotations

import base64
import json
from typing import Any

from ..handler_context import HandlerContext
from .response import text_content as _text_content


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(body: dict[str, Any]) -> str:
    data = body.get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _find_body_part(parts: list[dict[str, Any]], mime_type: str) -> str:
    """Recursively search parts tree for a body with the given MIME type."""
    for part in parts:
        if part.get("mimeType") == mime_type:
            text = _decode_body(part.get("body", {}))
            if text:
                return text
        sub_parts = part.get("parts", [])
        if sub_parts:
            text = _find_body_part(sub_parts, mime_type)
            if text:
                return text
    return ""


def _extract_body(payload: dict[str, Any]) -> str:
    """Extract body text from payload, recursing into nested multipart."""
    parts = payload.get("parts", [])
    if parts:
        text = _find_body_part(parts, "text/plain")
        if not text:
            text = _find_body_part(parts, "text/html")
        return text
    return _decode_body(payload.get("body", {}))


def _format_message(msg: dict[str, Any]) -> str:
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    from_addr = _get_header(headers, "From")
    to_addr = _get_header(headers, "To")
    subject = _get_header(headers, "Subject")
    date = _get_header(headers, "Date")

    body_text = _extract_body(payload)

    attachments = []
    for part in payload.get("parts", []):
        if part.get("filename"):
            att_id = part.get("body", {}).get("attachmentId", "")
            attachments.append(f"  - {part['filename']} (id: {att_id})")

    lines = [
        f"From: {from_addr}",
        f"To: {to_addr}",
        f"Subject: {subject}",
        f"Date: {date}",
        f"Message ID: {msg['id']}",
        f"Thread ID: {msg.get('threadId', '')}",
        f"Labels: {', '.join(msg.get('labelIds', []))}",
    ]
    if attachments:
        lines.append("Attachments:")
        lines.extend(attachments)
    lines.append("")
    lines.append(body_text)
    return "\n".join(lines)


def handle_get_profile(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    profile = ctx.client.get_profile()
    return _text_content(json.dumps(profile, indent=2))


def handle_search_messages(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    result = ctx.client.search_messages(
        q=args.get("q"),
        max_results=args.get("maxResults", 20),
        page_token=args.get("pageToken"),
        include_spam_trash=args.get("includeSpamTrash", False),
    )
    messages = result["messages"]
    if not messages:
        return _text_content("No messages found.")
    lines = [f"Found {result['resultSizeEstimate']} results:"]
    for msg in messages:
        lines.append(f"  - id: {msg['id']}  threadId: {msg['threadId']}")
    if result.get("nextPageToken"):
        lines.append(f"\nNext page token: {result['nextPageToken']}")
    return _text_content("\n".join(lines))


def handle_read_message(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    message_id = args.get("messageId")
    if not message_id:
        raise ValueError("messageId is required")
    msg = ctx.client.read_message(message_id)
    return _text_content(_format_message(msg))


def handle_read_thread(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    thread_id = args.get("threadId")
    if not thread_id:
        raise ValueError("threadId is required")
    thread = ctx.client.read_thread(thread_id)
    lines = [f"Thread: {thread['id']}", f"Messages: {len(thread['messages'])}", "---"]
    for msg in thread["messages"]:
        lines.append(_format_message(msg))
        lines.append("---")
    return _text_content("\n".join(lines))
