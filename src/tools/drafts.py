from __future__ import annotations

from typing import Any

from ..gmail_client import GmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def handle_create_draft(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    body = args.get("body")
    if not body:
        raise ValueError("body is required")
    result = client.create_draft(
        to=args.get("to"),
        subject=args.get("subject"),
        body=body,
        content_type=args.get("contentType", "text/plain"),
        cc=args.get("cc"),
        bcc=args.get("bcc"),
        thread_id=args.get("threadId"),
        attachments=args.get("attachments"),
    )
    return _text_content(
        f"Draft created.\nDraft ID: {result['id']}\n"
        f"Message ID: {result['message']['id']}\n"
        f"Use gmail_send_draft with draftId '{result['id']}' to send."
    )


def handle_update_draft(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    draft_id = args.get("draftId")
    if not draft_id:
        raise ValueError("draftId is required")
    result = client.update_draft(
        draft_id=draft_id,
        to=args.get("to"),
        subject=args.get("subject"),
        body=args.get("body", ""),
        content_type=args.get("contentType", "text/plain"),
        cc=args.get("cc"),
        bcc=args.get("bcc"),
        attachments=args.get("attachments"),
    )
    return _text_content(f"Draft updated.\nDraft ID: {result['id']}")


def handle_list_drafts(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    result = client.list_drafts(
        max_results=args.get("maxResults", 20), page_token=args.get("pageToken")
    )
    drafts = result["drafts"]
    if not drafts:
        return _text_content("No drafts found.")
    lines = [f"Found {len(drafts)} drafts:"]
    for d in drafts:
        lines.append(f"  - Draft ID: {d['id']}")
    if result.get("nextPageToken"):
        lines.append(f"\nNext page token: {result['nextPageToken']}")
    return _text_content("\n".join(lines))


def handle_send_draft(args: dict[str, Any], client: GmailClient) -> dict[str, Any]:
    draft_id = args.get("draftId")
    if not draft_id:
        raise ValueError("draftId is required")
    result = client.send_draft(draft_id)
    return _text_content(
        f"Draft sent successfully.\nMessage ID: {result['id']}\n"
        f"Labels: {', '.join(result.get('labelIds', []))}"
    )
