# Email Hygiene UI — Design Spec

**Date:** 2026-04-01
**Phase:** 3.6
**Status:** Approved

## Overview

Single-page web app for email triage, priority sender management, and newsletter cleanup. Served as static files from the existing MCP HTTP server. Communicates via JSON-RPC tool calls to the same endpoint Claude uses. No build step, no framework, vanilla HTML/CSS/JS.

## Architecture

```
Browser (fetch) → POST /mcp/ (JSON-RPC) → ToolRegistry.execute_tool() → GmailClient
Static files:     GET /ui/*             → src/ui/ directory
```

- Embedded in the existing HTTP server via `/ui/*` static file route on port 8420
- Same `MCP_AUTH_TOKEN` bearer auth used by Claude
- Works on desktop and mobile via Tailscale (`http://jons-mac-mini:8420/ui/`)
- No build system. Three static files: `index.html`, `app.js`, `style.css`

## Auth

Token read from URL query param (`/ui/?token=xxx`) or prompted on first load and stored in `localStorage`. Same bearer token as MCP access. Token passed as `Authorization: Bearer <token>` header on all JSON-RPC requests.

## Tabs

### Tab 1: Inbox Review (default)

**Account Switcher:** Toggle between Gmail and Outlook accounts at the top.

**Filter Chips** (always visible, horizontally scrollable):
- Needs Attention (unread/total) — CRITICAL + HIGH scored messages
- Unread (unread/total)
- People (unread/total) — from contacts/priority senders only
- Newsletters (unread/total) — detected via List-Unsubscribe header
- Promotional (unread/total) — Gmail category:promotions
- Unknown Senders (unread/total) — not in contacts or priority list, highlighted red
- Custom — free-text Gmail search query

Counts show `unread/total` format. Active filter chip is highlighted. Default filter: Needs Attention.

**Sort Options:** Priority Score (default), Date, Sender.

**Message List:**
- Each row: checkbox, priority dot (color-coded), sender name+email, subject preview, labels/tags, timestamp, per-message action icons
- Priority dot colors: red=CRITICAL, orange=HIGH, green=NORMAL, gray=LOW, dim red=JUNK
- Per-message actions: Archive, Trash, Spam, Block, Label dropdown, Add to Priority (star icon on unknown senders)
- Newsletter messages show inline Unsubscribe button
- Pagination: 50 messages per page

**Bulk Action Bar** (appears when checkboxes selected):
- Shows selected count
- Buttons: Move to label (dropdown with existing + "Create new"), Trash, Report Spam, Block All Senders, Add Senders to Priority

**Data flow:**
1. On tab load: call `gmail_search_messages` with filter-appropriate query + `gmail_triage_inbox` for scoring
2. Render message list sorted by priority score
3. Filter chips: each runs a different query (e.g. `is:unread`, `category:promotions`, custom query)
4. Count computation: separate `gmail_search_messages` calls per filter to get `resultSizeEstimate`

### Tab 2: Priority Senders

**List View:** Grouped by tier (Critical, High, Normal) with count per group.

Each entry shows: pattern, label, tier badge, remove button.

**Search/Filter Bar:** Filter the list by name or pattern.

**Add Sender Form:** Pattern input, tier dropdown, label input, Add button.

**Import Contacts Button:** Runs `gmail_import_contacts_as_priority` with tier=normal.

**Resync Contacts Button:** Re-pulls contacts from Google, adds new ones, skips patterns already in priority list AND patterns in the dismissed contacts list. Prevents accidentally re-adding removed contacts.

**Dismissed Contacts:** When a user removes a contact-origin priority sender, the pattern is added to a `dismissed_contacts` table in the triage SQLite cache. Resync checks this table before adding.

**Dismissed contacts table schema:**
```sql
CREATE TABLE IF NOT EXISTS dismissed_contacts (
    email_pattern TEXT PRIMARY KEY,
    dismissed_at TEXT NOT NULL
)
```

### Tab 3: Newsletters

**Auto-detection:** Scans recent inbox messages for List-Unsubscribe headers. Groups by sender domain/email.

**List View:** Each row shows:
- Sender name and email
- Count of emails from this sender
- Date of most recent email
- Unsubscribe link button (opens in new tab)
- Checkbox for bulk actions

Sorted by email count descending (most prolific first).

**Bulk Actions:** Trash all from sender, Block sender.

**Scan Inbox Button:** Refreshes newsletter detection by searching recent messages.

**Data flow:**
1. Search for messages with unsubscribe headers (query: `has:nousersubs OR unsubscribe`)
2. For each unique sender, count messages and extract unsubscribe link via `gmail_get_unsubscribe_link`
3. Render grouped list

## New MCP Tools (3)

### gmail_create_label

Create a new Gmail label.

- **Parameters:** `name: str`, `account: str | None`
- **GmailClient method:** `create_label(name)` calls `labels().create(userId="me", body={"name": name})`
- **Returns:** `{label_id: str, name: str}`

### gmail_dismiss_contact

Add a contact email pattern to the dismissed list (prevents resync from re-adding).

- **Parameters:** `pattern: str`, `account: str | None`
- **Cache method:** `dismiss_contact(pattern)` inserts into `dismissed_contacts` table
- **Returns:** confirmation text

### gmail_list_dismissed_contacts

List all dismissed contact patterns.

- **Parameters:** `account: str | None`
- **Cache method:** `get_dismissed_contacts()` queries `dismissed_contacts` table
- **Returns:** list of dismissed patterns with timestamps

## Tool Mapping

| UI Action | MCP Tool |
|-----------|----------|
| Load messages | `gmail_search_messages` + `gmail_triage_inbox` |
| Trash selected | `gmail_trash_messages` |
| Report spam | `gmail_report_spam` |
| Block sender | `gmail_block_sender` |
| Move to label | `gmail_modify_thread_labels` |
| Create label | `gmail_create_label` (NEW) |
| Add priority sender | `gmail_add_priority_sender` |
| Remove priority sender | `gmail_remove_priority_sender` |
| List priority senders | `gmail_list_priority_senders` |
| Import contacts | `gmail_import_contacts_as_priority` |
| Resync contacts | `gmail_import_contacts_as_priority` (checks dismissed list) |
| Dismiss contact | `gmail_dismiss_contact` (NEW) |
| List dismissed | `gmail_list_dismissed_contacts` (NEW) |
| Get unsubscribe link | `gmail_get_unsubscribe_link` |
| List labels | `gmail_list_labels` |
| Read message | `gmail_read_message` |
| Switch account | `gmail_list_accounts` |

Total tools after: 31 (28 existing + 3 new).

## File Structure

```
src/ui/
  index.html          — page shell, tab navigation, layout (~100 lines)
  app.js              — MCP client, tab controllers, DOM rendering (~400 lines)
  style.css           — dark theme, responsive, mobile-friendly (~200 lines)

src/http_server.py    — add /ui/* static file route
src/gmail_client.py   — add create_label method
src/tools/hygiene.py  — add handle_create_label, handle_dismiss_contact, handle_list_dismissed_contacts
src/tools/__init__.py — register 3 new tools (31 total)
src/triage/cache.py   — add dismissed_contacts table + CRUD methods
```

## Visual Design

- Dark theme matching the mockup: `#1a1a2e` background, `#16213e` panels
- Accent colors: `#e94560` (critical/active), `#f4a261` (high), `#4ecca3` (normal), `#666` (low)
- Responsive: works on desktop and mobile (Tailscale phone access)
- Touch-friendly: 44px minimum tap targets
- No emojis in production — use SVG icons or CSS-only indicators

## Mobile Considerations

- Horizontal scroll for filter chips
- Collapsible bulk action bar
- Swipe gestures not required (checkbox + tap actions sufficient)
- URL: `http://jons-mac-mini:8420/ui/?token=xxx`
