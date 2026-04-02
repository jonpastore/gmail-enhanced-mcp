from __future__ import annotations

from typing import Any

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
    {
        "name": "gmail_summarize_thread",
        "description": (
            "Summarize a thread: participants, timeline, key asks," " deadlines, open questions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string", "description": "The thread ID to summarize"},
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "gmail_needs_reply",
        "description": "Find emails that likely need a response from you.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "maxResults": {
                    "type": "integer",
                    "default": 20,
                    "description": "Max results to return",
                },
                "daysBack": {
                    "type": "integer",
                    "default": 7,
                    "description": "How many days back to search",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_batch_reply",
        "description": "Create draft replies for multiple messages in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "replies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "messageId": {"type": "string"},
                            "threadId": {"type": "string"},
                            "body": {"type": "string"},
                            "subject": {"type": "string"},
                        },
                        "required": ["messageId", "threadId", "body"],
                    },
                    "description": "List of replies to create as drafts",
                },
            },
            "required": ["replies"],
        },
    },
    {
        "name": "gmail_extract_itinerary",
        "description": (
            "Scan emails for travel bookings and return a structured" " itinerary timeline."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dateFrom": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD). Default: today.",
                },
                "dateTo": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD). Default: 30 days ahead.",
                },
                "maxResults": {
                    "type": "integer",
                    "default": 50,
                    "description": "Max emails to scan",
                },
            },
            "required": [],
        },
    },
]

for _tool in TOOL_DEFINITIONS:
    if _tool["name"] != "gmail_list_accounts":
        _tool["inputSchema"]["properties"].update(_ACCOUNT_PROP)
