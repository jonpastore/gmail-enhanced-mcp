from __future__ import annotations
from typing import Any
from ..gmail_client import GmailClient

def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}

def handle_send_email(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    to = args.get("to")
    if not to:
        raise ValueError("to is required")
    body = args.get("body")
    if not body:
        raise ValueError("body is required")
    result = client.send_email(
        to=to, subject=args.get("subject", ""), body=body,
        content_type=args.get("contentType", "text/plain"),
        cc=args.get("cc"), bcc=args.get("bcc"), attachments=args.get("attachments"),
    )
    return _text_content(f"Email sent successfully.\nMessage ID: {result['id']}\nLabels: {', '.join(result.get('labelIds', []))}")
