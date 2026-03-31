from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..models import ToolCallParams
from .attachments import handle_download_attachment
from .drafts import handle_create_draft, handle_list_drafts, handle_send_draft, handle_update_draft
from .labels import handle_list_labels, handle_modify_thread_labels
from .search import (
    handle_get_profile,
    handle_read_message,
    handle_read_thread,
    handle_search_messages,
)
from .send import handle_send_email
from .templates import handle_save_template, handle_use_template

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
        "name": "gmail_list_accounts",
        "description": "List all registered email accounts.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
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
}


class ToolRegistry:
    def __init__(self, account_registry: AccountRegistry | None = None) -> None:
        self._registry = account_registry
        self._tools = {t["name"]: t for t in TOOL_DEFINITIONS}
        self._handlers = dict(_HANDLER_MAP)

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    def execute_tool(self, params: ToolCallParams) -> dict[str, Any]:
        if params.name == "gmail_list_accounts":
            return self._handle_list_accounts()
        handler = self._handlers.get(params.name)
        if handler is None:
            raise ValueError(f"Unknown tool: {params.name}")
        logger.info(f"Executing tool: {params.name}")
        args = dict(params.arguments)
        account = args.pop("account", None)
        client = self._registry.get(account) if self._registry else None
        return handler(args, client)  # type: ignore[no-any-return]

    def _handle_list_accounts(self) -> dict[str, Any]:
        if self._registry is None:
            accounts: list[dict[str, Any]] = []
        else:
            accounts = self._registry.list_accounts()
        text = json.dumps(accounts, indent=2)
        return {"content": [{"type": "text", "text": text}]}
