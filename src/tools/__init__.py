from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..models import ToolCallParams
from ..triage.cache import TriageCache
from .attachments import handle_download_attachment
from .calendar import (
    handle_check_email_conflicts,
    handle_meeting_prep,
    handle_today_briefing,
)
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
from .labels import handle_list_labels, handle_modify_thread_labels
from .search import (
    handle_get_profile,
    handle_read_message,
    handle_read_thread,
    handle_search_messages,
)
from .send import handle_send_email
from .templates import handle_save_template, handle_use_template
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

_ACCOUNT_PROP = {
    "account": {
        "type": "string",
        "description": "Account email (e.g. jon@degenito.ai). Omit for default.",
    }
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "gmail_get_profile",
        "description": "Get the authenticated user's Gmail profile information.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gmail_search_messages",
        "description": "Search Gmail messages using query syntax.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Gmail search query"},
                "maxResults": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum number of results",
                },
                "pageToken": {"type": "string", "description": "Token for pagination"},
                "includeSpamTrash": {
                    "type": "boolean",
                    "description": "Include spam and trash results",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_read_message",
        "description": "Read a specific Gmail message by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageId": {"type": "string", "description": "The message ID to read"},
            },
            "required": ["messageId"],
        },
    },
    {
        "name": "gmail_read_thread",
        "description": "Read all messages in a Gmail thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string", "description": "The thread ID to read"},
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "gmail_download_attachment",
        "description": "Download an email attachment to a local path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageId": {
                    "type": "string",
                    "description": "The message ID containing the attachment",
                },
                "attachmentId": {"type": "string", "description": "The attachment ID"},
                "savePath": {"type": "string", "description": "Local path to save the attachment"},
            },
            "required": ["messageId", "attachmentId", "savePath"],
        },
    },
    {
        "name": "gmail_create_draft",
        "description": "Create a new Gmail draft message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body content"},
                "cc": {"type": "string", "description": "CC recipients"},
                "bcc": {"type": "string", "description": "BCC recipients"},
                "contentType": {
                    "type": "string",
                    "enum": ["text/plain", "text/html"],
                    "description": "Content type",
                },
                "threadId": {"type": "string", "description": "Thread ID for replies"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "File attachments",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "gmail_update_draft",
        "description": "Update an existing Gmail draft.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "draftId": {"type": "string", "description": "The draft ID to update"},
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body content"},
                "cc": {"type": "string", "description": "CC recipients"},
                "bcc": {"type": "string", "description": "BCC recipients"},
                "contentType": {
                    "type": "string",
                    "enum": ["text/plain", "text/html"],
                    "description": "Content type",
                },
                "attachments": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "File attachments",
                },
            },
            "required": ["draftId"],
        },
    },
    {
        "name": "gmail_list_drafts",
        "description": "List Gmail drafts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "maxResults": {"type": "integer", "description": "Maximum number of results"},
                "pageToken": {"type": "string", "description": "Token for pagination"},
            },
            "required": [],
        },
    },
    {
        "name": "gmail_send_draft",
        "description": "Send an existing Gmail draft. Always let user review before sending.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "draftId": {"type": "string", "description": "The draft ID to send"},
            },
            "required": ["draftId"],
        },
    },
    {
        "name": "gmail_send_email",
        "description": "Send an email directly. Confirm with user before sending.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body content"},
                "cc": {"type": "string", "description": "CC recipients"},
                "bcc": {"type": "string", "description": "BCC recipients"},
                "contentType": {
                    "type": "string",
                    "enum": ["text/plain", "text/html"],
                    "description": "Content type",
                },
                "attachments": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "File attachments",
                },
            },
            "required": ["to", "body"],
        },
    },
    {
        "name": "gmail_list_labels",
        "description": "List all Gmail labels.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gmail_modify_thread_labels",
        "description": "Add or remove labels from a Gmail thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string", "description": "The thread ID to modify"},
                "addLabelIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label IDs to add",
                },
                "removeLabelIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label IDs to remove",
                },
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "gmail_save_template",
        "description": "Save an email template for reuse.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name"},
                "subject": {"type": "string", "description": "Email subject template"},
                "body": {"type": "string", "description": "Email body template"},
                "contentType": {
                    "type": "string",
                    "enum": ["text/plain", "text/html"],
                    "description": "Content type",
                },
                "variables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Template variable names",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "gmail_use_template",
        "description": "Create a draft from a saved template with variable substitution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name"},
                "variables": {
                    "type": "object",
                    "description": "Variable key-value pairs for substitution",
                },
                "to": {"type": "string", "description": "Recipient email address"},
                "cc": {"type": "string", "description": "CC recipients"},
                "bcc": {"type": "string", "description": "BCC recipients"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "File attachments",
                },
            },
            "required": ["name", "variables"],
        },
    },
    {
        "name": "gmail_triage_inbox",
        "description": (
            "Score, detect junk, and suggest sorting for a batch of messages."
            " Returns importance scores, junk flags, and label proposals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query (e.g. 'is:unread')"},
                "maxResults": {
                    "type": "integer",
                    "default": 20,
                    "description": "Max messages to triage",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_add_priority_sender",
        "description": "Add an email or domain pattern to the priority sender list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Email or domain glob (e.g. '*@irs.gov')",
                },
                "tier": {
                    "type": "string",
                    "enum": ["critical", "high", "normal"],
                    "description": "Priority tier",
                },
                "label": {
                    "type": "string",
                    "description": "Human-readable label (e.g. 'Government')",
                },
            },
            "required": ["pattern", "tier", "label"],
        },
    },
    {
        "name": "gmail_list_priority_senders",
        "description": "List all priority sender patterns grouped by tier.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gmail_remove_priority_sender",
        "description": "Remove a priority sender pattern.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Pattern to remove"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "gmail_track_followup",
        "description": "Start tracking a sent message for follow-up replies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageId": {
                    "type": "string",
                    "description": "The sent message ID to track",
                },
                "expectedDays": {
                    "type": "integer",
                    "default": 3,
                    "description": "Days to expect a reply",
                },
            },
            "required": ["messageId"],
        },
    },
    {
        "name": "gmail_check_followups",
        "description": (
            "Check all tracked follow-ups for replies," " overdue items, and approaching deadlines."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "includeOverdue": {"type": "boolean", "default": True},
                "includeApproachingDeadline": {"type": "boolean", "default": True},
                "withinDays": {
                    "type": "integer",
                    "default": 2,
                    "description": "Days ahead for deadline check",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_reset_triage_cache",
        "description": "Reset the triage cache (delete all cached data). Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {
                    "type": "boolean",
                    "description": "Must be true to confirm reset",
                },
            },
            "required": ["confirm"],
        },
    },
    {
        "name": "gmail_list_accounts",
        "description": "List all registered email accounts.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gmail_trash_messages",
        "description": "Trash messages by IDs or search query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of message IDs to trash",
                },
                "query": {
                    "type": "string",
                    "description": "Gmail search query to find messages to trash",
                },
                "maxResults": {
                    "type": "integer",
                    "default": 500,
                    "description": "Max messages to trash when using query",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_block_sender",
        "description": "Block a sender: create auto-delete filter and trash existing messages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Email address or domain to block",
                },
            },
            "required": ["sender"],
        },
    },
    {
        "name": "gmail_report_spam",
        "description": "Report messages as spam (trains Gmail spam filter).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Message IDs to report as spam",
                },
            },
            "required": ["messageIds"],
        },
    },
    {
        "name": "gmail_list_contacts",
        "description": "List Google contacts with email addresses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "maxResults": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Max contacts to return",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_import_contacts_as_priority",
        "description": "Import Google contacts as priority senders at a specified tier.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tier": {
                    "type": "string",
                    "enum": ["critical", "high", "normal"],
                    "default": "normal",
                    "description": "Priority tier for imported contacts",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_get_unsubscribe_link",
        "description": "Extract unsubscribe link from a message's List-Unsubscribe header.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageId": {
                    "type": "string",
                    "description": "Message ID to extract unsubscribe link from",
                },
            },
            "required": ["messageId"],
        },
    },
    {
        "name": "gmail_create_label",
        "description": "Create a new Gmail label.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Label name to create",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "gmail_dismiss_contact",
        "description": "Dismiss a contact pattern so resync won't re-add it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Email pattern to dismiss",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "gmail_list_dismissed_contacts",
        "description": "List all dismissed contact patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "gmail_check_email_conflicts",
        "description": "Scan emails for date/time mentions and cross-reference against calendar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Gmail search query to filter emails"},
                "maxResults": {
                    "type": "integer",
                    "default": 10,
                    "description": "Max emails to scan",
                },
                "daysAhead": {
                    "type": "integer",
                    "default": 7,
                    "description": "How many days ahead to check for conflicts",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_meeting_prep",
        "description": "Surface relevant email threads for an upcoming calendar event.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "eventId": {
                    "type": "string",
                    "description": "Specific event ID to prep for",
                },
                "hoursAhead": {
                    "type": "integer",
                    "default": 4,
                    "description": "Hours ahead to look for upcoming meetings",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_today_briefing",
        "description": "Combined inbox triage + calendar overview for the day.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "includeCalendar": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include calendar events in briefing",
                },
                "maxEmails": {
                    "type": "integer",
                    "default": 20,
                    "description": "Max unread emails to triage",
                },
            },
            "required": [],
        },
    },
]

for _tool in TOOL_DEFINITIONS:
    if _tool["name"] != "gmail_list_accounts":
        _tool["inputSchema"]["properties"].update(_ACCOUNT_PROP)

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
}

_CALENDAR_HANDLER_MAP: dict[str, Any] = {
    "gmail_check_email_conflicts": handle_check_email_conflicts,
    "gmail_meeting_prep": handle_meeting_prep,
    "gmail_today_briefing": handle_today_briefing,
}

_TRIAGE_HANDLER_MAP: dict[str, Any] = {
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
        self._triage_handlers = dict(_TRIAGE_HANDLER_MAP)
        self._calendar_handlers = dict(_CALENDAR_HANDLER_MAP)
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

        calendar_handler = self._calendar_handlers.get(params.name)
        if calendar_handler is not None:
            logger.info(f"Executing calendar tool: {params.name}")
            if self._calendar_ctx is None:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Error: Calendar not configured. "
                                "Set CALENDAR_ENABLED=true and run: python -m gmail_mcp auth"
                            ),
                        }
                    ],
                    "isError": True,
                }
            return calendar_handler(args, client, self._calendar_ctx, self._triage_cache)  # type: ignore[no-any-return]

        triage_handler = self._triage_handlers.get(params.name)
        if triage_handler is not None:
            logger.info(f"Executing triage tool: {params.name}")
            return triage_handler(args, client, self._triage_cache)  # type: ignore[no-any-return]

        handler = self._handlers.get(params.name)
        if handler is None:
            raise ValueError(f"Unknown tool: {params.name}")
        logger.info(f"Executing tool: {params.name}")
        return handler(args, client)  # type: ignore[no-any-return]

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
