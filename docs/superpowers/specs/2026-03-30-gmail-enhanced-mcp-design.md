# Gmail Enhanced MCP — Phase 1 Design Spec

## Overview

A Python MCP server providing full Gmail API access via Claude Code's stdio transport, with attachment support — the key capability missing from Claude.ai's native Gmail connector.

**Account**: jpastore79@gmail.com (personal Gmail)
**Transport**: Stdio (JSON-RPC 2.0), migrating to HTTP SSE in Phase 2
**Language**: Python 3.11+
**Pattern**: Modeled on chatgpt5-mcp-server reference implementation

## Phased Roadmap

| Phase | Scope |
|-------|-------|
| **1 (this spec)** | Core Gmail MCP — search, read, draft+attachments, send, send-draft, labels, templates |
| 2 | Multi-account (additional Gmail + Outlook.com via Microsoft Graph) + migrate to HTTP SSE transport |
| 3 | Email triage + organization — importance scoring, junk/unsubscribe detection, auto-sort proposals, priority sender lists, follow-up tracker, deadline extraction |
| 4 | Calendar conflict monitoring — cross-calendar awareness across Google + Outlook |
| 5 | AI response drafting — proposed replies with conversation summary and reasoning, travel itinerary aggregation |
| 6 | Smart digest — scheduled summaries across all accounts, contact intelligence |

All phases: no action without user approval.

## Architecture

```
claude-code (stdio) <-> gmail-enhanced-mcp (Python subprocess)
                              |
                        Google Gmail API v1
                              |
                        jpastore79@gmail.com
```

### Project Structure

```
gmail-enhanced-mcp/
├── src/
│   ├── __init__.py
│   ├── main.py           # Entry point, launches stdio server
│   ├── server.py          # Stdin/stdout JSON-RPC communication
│   ├── protocol.py        # MCP method routing (initialize, tools/list, tools/call)
│   ├── models.py          # Pydantic models for requests/responses
│   ├── config.py          # Config + logging setup
│   ├── auth.py            # OAuth2 flow + token management
│   ├── gmail_client.py    # Gmail API wrapper (single point of API contact)
│   └── tools/
│       ├── __init__.py
│       ├── search.py      # search_messages, read_message, read_thread
│       ├── drafts.py      # create_draft, list_drafts, update_draft, send_draft
│       ├── send.py        # send_email (direct send with attachments)
│       ├── labels.py      # list_labels, create_label, modify_thread_labels
│       ├── attachments.py # download_attachment, attachment resolution helpers
│       └── templates.py   # save_template, list_templates, use_template
├── templates/             # Saved email templates (JSON)
├── credentials/           # OAuth tokens (gitignored)
├── tests/
│   ├── conftest.py        # Shared fixtures, Gmail API mocks
│   ├── unit/
│   │   ├── test_auth.py
│   │   ├── test_gmail_client.py
│   │   ├── test_models.py
│   │   ├── test_protocol.py
│   │   ├── test_server.py
│   │   └── tools/
│   │       ├── test_search.py
│   │       ├── test_drafts.py
│   │       ├── test_send.py
│   │       ├── test_labels.py
│   │       ├── test_attachments.py
│   │       └── test_templates.py
│   └── integration/
│       ├── test_stdio_roundtrip.py
│       └── test_gmail_api.py    # Requires real credentials (#[ignore] equivalent)
├── requirements.txt
├── pyproject.toml
├── package.json           # MCP command config for Claude Code
├── .env.example
└── README.md
```

### Key Design Decisions

- `gmail_client.py` is the single point of contact with Google's API — tools never call the API directly
- Attachments handled via MIME multipart construction before sending to API
- Token refresh is automatic and transparent within `gmail_client.py`
- All tools return structured JSON responses matching MCP content format

## Tools

### Read Operations (4 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_get_profile` | — | Account info + stats |
| `gmail_search_messages` | q, maxResults, pageToken, includeSpamTrash | Full Gmail search syntax |
| `gmail_read_message` | messageId | Full message with headers, body, attachment metadata |
| `gmail_read_thread` | threadId | All messages in a thread |

### Attachment Operations (1 tool)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_download_attachment` | messageId, attachmentId, savePath | Save attachment to local disk |

### Draft Operations (4 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_create_draft` | to, subject, body, cc, bcc, contentType, threadId, **attachments** | Draft with file attachments |
| `gmail_update_draft` | draftId, to, subject, body, cc, bcc, contentType, **attachments** | Modify existing draft |
| `gmail_list_drafts` | maxResults, pageToken | List all drafts |
| `gmail_send_draft` | draftId | Send an existing draft |

### Send Operations (1 tool)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_send_email` | to, subject, body, cc, bcc, contentType, **attachments** | Direct send with attachments |

### Label Operations (2 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_list_labels` | — | All system + user labels |
| `gmail_modify_thread_labels` | threadId, addLabelIds, removeLabelIds | Add/remove labels |

### Template Operations (2 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_save_template` | name, subject, body, contentType, variables | Save reusable template |
| `gmail_use_template` | name, variables, to, cc, bcc, attachments | Render template into draft |

### Attachment Parameter Format

The `attachments` parameter accepts a JSON array:

```json
[
  {"type": "file", "path": "/home/jon/Downloads/claim.pdf"},
  {"type": "gmail", "messageId": "abc123", "attachmentId": "def456"},
  {"type": "url", "url": "https://example.com/doc.pdf", "filename": "doc.pdf"}
]
```

Three sources:
1. **Local file** (`type: "file"`) — reads from disk, auto-detects MIME type via `mimetypes`
2. **Gmail attachment** (`type: "gmail"`) — fetches via `messages.attachments.get()`
3. **URL fetch** (`type: "url"`) — HTTP GET, 30s timeout, 25MB limit, requires explicit `filename`

### MIME Construction Pipeline

```
Tool call with attachments[]
    -> gmail_client.py validates each attachment source
    -> Resolves to bytes + filename + mime_type per attachment
    -> Builds multipart/mixed MIME message
    -> Base64url encodes for Gmail API
    -> Sends via messages.send() or drafts.create()
```

Limits:
- Gmail API max message size: 35MB (after base64 encoding ~25MB raw)
- Validation before API call — reject oversized with clear error
- No silent truncation
- Inline images in HTML: supported via Content-ID headers
- `.eml` attachments: supported as `message/rfc822` MIME type

## Authentication

### One-Time Setup

1. User creates OAuth2 client in Google Cloud Console
2. Downloads `client_secret.json` to `credentials/`
3. Runs `python -m gmail_mcp auth`
4. Temporary localhost server spins up, browser opens consent screen
5. User grants scopes
6. Token saved to `credentials/token.json` (gitignored)

### OAuth2 Scopes

- `gmail.modify` — read, label, trash (covers search/read/labels)
- `gmail.compose` — create/update drafts
- `gmail.send` — send messages and drafts
- NOT `mail.google.com` — principle of least privilege

### Runtime Token Management

- Token loaded on first tool call, cached in memory
- Auto-refreshes expired tokens using refresh_token
- If refresh fails (revoked): clear error directing user to re-auth

## Template System

Templates stored as JSON in `templates/`:

```json
{
  "name": "insurance_claim",
  "subject": "{{claim_type}} Claim - {{policy_number}} - {{trip_dates}}",
  "body": "Dear {{recipient_name}},\n\nI am filing a {{claim_type}} claim...",
  "contentType": "text/plain",
  "variables": ["claim_type", "policy_number", "trip_dates", "recipient_name"]
}
```

- `gmail_save_template` — validates `{{placeholders}}` match declared variables
- `gmail_use_template` — renders with provided variables, creates a **draft** (never sends)
- Missing variables → error listing what's missing
- Simple `str.replace()` — no inheritance, conditionals, or loops

## Error Handling

### Gmail API Errors → Actionable MCP Responses

| API Error | MCP Error Message |
|-----------|-------------------|
| 401 Unauthorized | "Token expired. Re-run `python -m gmail_mcp auth`" |
| 403 Insufficient permissions | "Missing scope. Re-auth with: `python -m gmail_mcp auth`" |
| 404 Not found | "Message/draft not found: {id}" |
| 429 Rate limited | "Rate limited — wait 60s and retry" |
| 400 Invalid request | "Invalid parameter: {detail}" |

### Attachment-Specific Errors

- File not found → "Attachment path does not exist: /path/to/file"
- Oversized → "Attachment exceeds 25MB limit: filename (32MB)"
- URL fetch failure → "Failed to fetch URL: connection timeout after 30s"
- Invalid MIME → "Cannot determine file type for: filename"

### No Auto-Retry

Send operations are never retried automatically. Rate limit errors return guidance, user decides.

## Safety Rails

### NEVER Rules

1. NEVER send an email without explicit user approval
2. NEVER log email body content at any log level
3. NEVER log OAuth tokens or credentials
4. NEVER expose recipient lists in error messages
5. NEVER auto-retry a send operation on failure
6. NEVER store credentials outside `credentials/` directory

### Logging Policy

- **Log**: tool call names + parameter names (not values), API response codes, auth refresh events
- **Never log**: message bodies, attachment contents, email addresses, tokens
- Loguru with file rotation (10MB, 3 backups)

## Dependencies

```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
pydantic>=2.5.0,<3.0.0
python-dotenv>=1.0.0
loguru>=0.7.0
requests>=2.31.0
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-asyncio>=0.24.0
mypy>=1.8.0
ruff>=0.3.0
black>=24.0.0
```

## Testing Strategy

- **Unit tests**: Mock Gmail API responses via `unittest.mock`, test each tool in isolation
- **Integration tests**: Stdio JSON-RPC roundtrips with mocked gmail_client
- **Live tests**: Marked with `@pytest.mark.live`, require real credentials, excluded from CI
- **TDD**: All features built test-first using superpowers:test-driven-development skill
- **Coverage target**: 90%+ for src/, excluding auth.py live OAuth flow
