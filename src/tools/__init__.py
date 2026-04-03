from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..handler_context import HandlerContext
from ..models import ToolCallParams
from ..triage.cache import TriageCache
from .ai_context import handle_needs_reply, handle_summarize_thread
from .attachments import handle_download_attachment
from .batch_reply import handle_batch_reply
from .calendar import (
    handle_check_email_conflicts,
    handle_meeting_prep,
    handle_today_briefing,
)
from .digest import handle_generate_digest
from .drafts import handle_create_draft, handle_list_drafts, handle_send_draft, handle_update_draft
from .hygiene import (
    handle_block_sender,
    handle_create_label,
    handle_dismiss_contact,
    handle_get_unsubscribe_link,
    handle_import_contacts_as_priority,
    handle_list_contacts,
    handle_list_dismissed_contacts,
    handle_report_spam,
    handle_trash_messages,
)
from .itinerary import handle_extract_itinerary
from .labels import handle_list_labels, handle_modify_thread_labels
from .search import (
    handle_get_profile,
    handle_read_message,
    handle_read_thread,
    handle_search_messages,
)
from .send import handle_send_email
from .templates import handle_save_template, handle_use_template
from .tool_schemas import TOOL_DEFINITIONS
from .triage import (
    handle_add_priority_sender,
    handle_check_followups,
    handle_list_priority_senders,
    handle_remove_priority_sender,
    handle_reset_triage_cache,
    handle_track_followup,
    handle_triage_inbox,
)

if TYPE_CHECKING:
    from ..account_registry import AccountRegistry

_HANDLER_MAP: dict[str, Any] = {
    "gmail_get_profile": handle_get_profile,
    "gmail_search_messages": handle_search_messages,
    "gmail_read_message": handle_read_message,
    "gmail_read_thread": handle_read_thread,
    "gmail_download_attachment": handle_download_attachment,
    "gmail_create_draft": handle_create_draft,
    "gmail_update_draft": handle_update_draft,
    "gmail_list_drafts": handle_list_drafts,
    "gmail_send_draft": handle_send_draft,
    "gmail_send_email": handle_send_email,
    "gmail_list_labels": handle_list_labels,
    "gmail_modify_thread_labels": handle_modify_thread_labels,
    "gmail_save_template": handle_save_template,
    "gmail_use_template": handle_use_template,
    "gmail_trash_messages": handle_trash_messages,
    "gmail_block_sender": handle_block_sender,
    "gmail_report_spam": handle_report_spam,
    "gmail_list_contacts": handle_list_contacts,
    "gmail_get_unsubscribe_link": handle_get_unsubscribe_link,
    "gmail_create_label": handle_create_label,
    "gmail_summarize_thread": handle_summarize_thread,
    "gmail_needs_reply": handle_needs_reply,
    "gmail_batch_reply": handle_batch_reply,
    "gmail_extract_itinerary": handle_extract_itinerary,
    "gmail_triage_inbox": handle_triage_inbox,
    "gmail_add_priority_sender": handle_add_priority_sender,
    "gmail_list_priority_senders": handle_list_priority_senders,
    "gmail_remove_priority_sender": handle_remove_priority_sender,
    "gmail_track_followup": handle_track_followup,
    "gmail_check_followups": handle_check_followups,
    "gmail_reset_triage_cache": handle_reset_triage_cache,
    "gmail_import_contacts_as_priority": handle_import_contacts_as_priority,
    "gmail_dismiss_contact": handle_dismiss_contact,
    "gmail_list_dismissed_contacts": handle_list_dismissed_contacts,
    "gmail_check_email_conflicts": handle_check_email_conflicts,
    "gmail_meeting_prep": handle_meeting_prep,
    "gmail_today_briefing": handle_today_briefing,
    "gmail_generate_digest": handle_generate_digest,
}


class ToolRegistry:
    def __init__(
        self,
        account_registry: AccountRegistry | None = None,
        cache_db_path: str | None = None,
        calendar_ctx: Any | None = None,
    ) -> None:
        self._registry = account_registry
        self._tools = {t["name"]: t for t in TOOL_DEFINITIONS}
        self._handlers = dict(_HANDLER_MAP)
        self._calendar_ctx = calendar_ctx
        db_path = Path(cache_db_path) if cache_db_path else Path(":memory:")
        self._triage_cache = TriageCache(db_path)
        self._triage_cache.initialize()

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    def execute_tool(self, params: ToolCallParams) -> dict[str, Any]:
        if params.name == "gmail_list_accounts":
            return self._handle_list_accounts()

        args = dict(params.arguments)
        account = args.pop("account", None)
        client = self._registry.get(account) if self._registry else None

        handler = self._handlers.get(params.name)
        if handler is None:
            raise ValueError(f"Unknown tool: {params.name}")

        assert client is not None
        ctx = HandlerContext(
            client=client,
            cache=self._triage_cache,
            calendar_ctx=self._calendar_ctx,
        )
        logger.info(f"Executing tool: {params.name}")
        return handler(args, ctx)  # type: ignore[no-any-return]

    def close(self) -> None:
        """Close the triage cache on shutdown."""
        self._triage_cache.close()

    def _handle_list_accounts(self) -> dict[str, Any]:
        if self._registry is None:
            accounts: list[dict[str, Any]] = []
        else:
            accounts = self._registry.list_accounts()
        text = json.dumps(accounts, indent=2)
        return {"content": [{"type": "text", "text": text}]}
