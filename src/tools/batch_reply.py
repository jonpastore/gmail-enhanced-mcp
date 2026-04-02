"""Batch reply tool handler: create multiple draft replies in one call."""

from __future__ import annotations

from typing import Any

from ..handler_context import HandlerContext
from .response import error_content as _error_content
from .response import text_content as _text_content
from .search import _get_header

_MAX_REPLIES = 20


def handle_batch_reply(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """Create draft replies for multiple messages in a single call.

    Args:
        args: Tool arguments containing a ``replies`` list. Each entry must
            have ``messageId``, ``threadId``, and ``body``; ``subject`` is
            optional.
        ctx: Handler context with client for reading messages and creating drafts.

    Returns:
        MCP content with counts of drafts created and any per-reply errors.
    """
    import json

    replies: list[dict[str, Any]] = args.get("replies", [])

    if not replies:
        return _error_content("replies list is required and must not be empty")

    if len(replies) > _MAX_REPLIES:
        return _error_content(f"Maximum {_MAX_REPLIES} replies per batch; received {len(replies)}")

    draft_ids: list[str] = []
    errors: list[str] = []

    for entry in replies:
        message_id: str = entry.get("messageId", "")
        thread_id: str = entry.get("threadId", "")
        body: str = entry.get("body", "")
        subject_override: str | None = entry.get("subject")

        if not message_id or not thread_id or not body:
            errors.append(f"Skipped entry — missing messageId, threadId, or body: {entry!r}")
            continue

        try:
            original = ctx.client.read_message(message_id)
        except Exception as exc:
            errors.append(f"Could not read message {message_id}: {exc}")
            continue

        payload = original.get("payload", {})
        headers = payload.get("headers", [])
        from_addr = _get_header(headers, "From")
        original_subject = _get_header(headers, "Subject")

        if not from_addr:
            errors.append(f"Message {message_id} has no From header; skipping")
            continue

        reply_subject = subject_override or (
            original_subject
            if original_subject.lower().startswith("re:")
            else f"Re: {original_subject}"
        )

        try:
            draft = ctx.client.create_draft(
                to=from_addr,
                subject=reply_subject,
                body=body,
                thread_id=thread_id,
            )
            draft_id = draft.get("id", "")
            draft_ids.append(draft_id)
        except Exception as exc:
            errors.append(f"Draft creation failed for message {message_id}: {exc}")

    result = {
        "drafts_created": len(draft_ids),
        "draft_ids": draft_ids,
        "errors": errors,
    }
    return _text_content(json.dumps(result, indent=2))
