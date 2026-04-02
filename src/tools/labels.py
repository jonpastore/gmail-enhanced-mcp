from __future__ import annotations

from typing import Any

from ..handler_context import HandlerContext
from .response import text_content as _text_content


def handle_list_labels(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    labels = ctx.client.list_labels()
    lines = [f"Found {len(labels)} labels:"]
    for label in labels:
        lines.append(
            f"  - {label['name']} (id: {label['id']}, type: {label.get('type', 'unknown')})"
        )
    return _text_content("\n".join(lines))


def handle_modify_thread_labels(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    thread_id = args.get("threadId")
    if not thread_id:
        raise ValueError("threadId is required")
    result = ctx.client.modify_thread_labels(
        thread_id=thread_id,
        add_label_ids=args.get("addLabelIds"),
        remove_label_ids=args.get("removeLabelIds"),
    )
    return _text_content(f"Labels modified for thread: {result['id']}")
