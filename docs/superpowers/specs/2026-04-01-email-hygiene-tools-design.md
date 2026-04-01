# Email Hygiene Tools — Design Spec

**Date:** 2026-04-01
**Phase:** 3.5
**Status:** Approved

## Overview

Add 6 new MCP tools for email hygiene: trash, block, spam reporting, contacts import, contact listing, and unsubscribe link extraction. Gmail-only features built on existing `gmail.modify` scope plus newly added `contacts.readonly` scope.

## Tools

### gmail_trash_messages

Bulk trash messages by IDs or search query.

**Parameters:**
- `message_ids: list[str] | None` — specific message IDs to trash
- `query: str | None` — Gmail search query; trashes all matching results
- `max_results: int = 500` — max messages to trash when using query
- `account: str | None` — account email, omit for default

**Validation:** Must provide one of `message_ids` or `query`, not both.

**GmailClient method:** `trash_messages(message_ids)` calls `messages().trash()` per ID. `trash_by_query(query, max_results)` searches then trashes.

**Returns:** `{trashed_count: int, message_ids: list[str]}`

### gmail_block_sender

Create auto-delete filter for a sender and trash existing messages.

**Parameters:**
- `sender: str` — email address or domain (e.g. `spam@example.com` or `example.com`)
- `account: str | None`

**GmailClient method:** `create_block_filter(sender)` uses `settings().filters().create()` with criteria `from=sender`, action `removeLabelIds=["INBOX"], addLabelIds=["TRASH"]`. Then trashes existing messages via `trash_by_query(f"from:{sender}")`.

**Returns:** `{filter_id: str, existing_trashed: int}`

### gmail_report_spam

Move messages to spam (trains Gmail's spam filter).

**Parameters:**
- `message_ids: list[str]` — message IDs to report
- `account: str | None`

**GmailClient method:** `report_spam(message_ids)` calls `messages().batchModify()` with `addLabelIds=["SPAM"], removeLabelIds=["INBOX"]`.

**Returns:** `{reported_count: int}`

### gmail_list_contacts

List Google contacts with email addresses.

**Parameters:**
- `max_results: int = 2000` — max contacts to return
- `account: str | None`

**GmailClient method:** `get_contacts(max_results)` uses People API `people().connections().list()` with pagination. Filters to contacts that have at least one email address.

**Returns:** `{contacts: [{name: str, emails: [str]}], total: int}`

**Note:** Gmail accounts only. People API is Google-specific.

### gmail_import_contacts_as_priority

Import Google contacts as priority senders.

**Parameters:**
- `tier: str = "normal"` — priority tier (critical/high/normal)
- `account: str | None`

**Flow:**
1. Pull all contacts with emails via `get_contacts()`
2. Load existing priority sender patterns
3. For each contact email, check if it already matches an existing pattern
4. Add non-matching emails as priority senders with contact name as label
5. Return summary

**Returns:** `{added: int, skipped: int, total_contacts: int}`

### gmail_get_unsubscribe_link

Extract unsubscribe link from a message's headers.

**Parameters:**
- `message_id: str` — message ID to inspect
- `account: str | None`

**GmailClient method:** `extract_unsubscribe_link(message_id)` reads message headers for `List-Unsubscribe`. Parses both `mailto:` and `https:` variants. Returns without executing.

**Returns:** `{unsubscribe_url: str | None, unsubscribe_mailto: str | None, found: bool}`

## Architecture

### GmailClient Changes

6 new methods on `GmailClient` (not on `EmailClient` ABC — these are Gmail/Google-specific):

- `trash_messages(message_ids: list[str]) -> dict`
- `trash_by_query(query: str, max_results: int = 500) -> dict`
- `create_block_filter(sender: str) -> dict`
- `report_spam(message_ids: list[str]) -> dict`
- `get_contacts(max_results: int = 2000) -> list[dict]`
- `extract_unsubscribe_link(message_id: str) -> dict`

### New Tool File

`src/tools/hygiene.py` — 6 handler functions following existing tool patterns. Each validates inputs via Pydantic, calls GmailClient methods, returns MCP content format.

### Provider Guard

All 6 tools check `client.provider == "gmail"`. If called with an Outlook account, return error: "This tool is only available for Gmail accounts."

### Registration

Add 6 handlers to `src/tools/__init__.py` tool registry.

## OAuth Scopes

- `gmail.modify` — already present, covers trash, spam, filters
- `contacts.readonly` — added to `src/auth.py`, token re-created

## File Impact

| File | Change | Est. Lines |
|------|--------|-----------|
| `src/auth.py` | Done — scope added | +1 |
| `src/gmail_client.py` | +6 methods | +120 |
| `src/tools/hygiene.py` | New file, 6 handlers | ~180 |
| `src/tools/__init__.py` | Register 6 tools | +12 |
| `tests/unit/tools/test_hygiene.py` | New, unit tests | ~200 |
| `tests/unit/test_gmail_client.py` | Tests for new methods | +80 |

All files stay under 500-line limit. Total MCP tools after: 28 (22 + 6).

## Immediate Actions Post-Build

1. `gmail_import_contacts_as_priority(tier="normal")` — import 214 contacts
2. `gmail_trash_messages(query="from:earthbreeze")` — delete Earth Breeze (25 emails)
3. `gmail_trash_messages(query="from:game7staffing")` — delete Game 7 Staffing (10+ emails)

## Future: Email Hygiene UI

Separate phase. Web UI connecting to MCP server with:
- Checkbox list of emails grouped by sender/category
- Bulk approve/reject priority senders
- Select to trash, block, or report spam
- Unsubscribe recommendations
