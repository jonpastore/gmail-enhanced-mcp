from __future__ import annotations

from typing import Any

from ..email_client import EmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def handle_download_attachment(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    message_id = args.get("messageId")
    if not message_id:
        raise ValueError("messageId is required")
    attachment_id = args.get("attachmentId")
    if not attachment_id:
        raise ValueError("attachmentId is required")
    save_path = args.get("savePath")
    if not save_path:
        raise ValueError("savePath is required")
    saved = client.download_attachment(message_id, attachment_id, save_path)
    return _text_content(f"Attachment saved to: {saved}")
