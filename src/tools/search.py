from __future__ import annotations

import base64
import json
from typing import Any

from ..gmail_client import GmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


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


def _format_message(msg: dict[str, Any]) -> str:
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    from_addr = _get_header(headers, "From")
    to_addr = _get_header(headers, "To")
    subject = _get_header(headers, "Subject")
    date = _get_header(headers, "Date")

    body_text = ""
    if payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                body_text = _decode_body(part.get("body", {}))
                break
        if not body_text:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    body_text = _decode_body(part.get("body", {}))
                    break
    else:
        body_text = _decode_body(payload.get("body", {}))

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


def handle_get_profile(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    profile = client.get_profile()
    return _text_content(json.dumps(profile, indent=2))


def handle_search_messages(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    result = client.search_messages(
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


def handle_read_message(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    message_id = args.get("messageId")
    if not message_id:
        raise ValueError("messageId is required")
    msg = client.read_message(message_id)
    return _text_content(_format_message(msg))


def handle_read_thread(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    thread_id = args.get("threadId")
    if not thread_id:
        raise ValueError("threadId is required")
    thread = client.read_thread(thread_id)
    lines = [f"Thread: {thread['id']}", f"Messages: {len(thread['messages'])}", "---"]
    for msg in thread["messages"]:
        lines.append(_format_message(msg))
        lines.append("---")
    return _text_content("\n".join(lines))
