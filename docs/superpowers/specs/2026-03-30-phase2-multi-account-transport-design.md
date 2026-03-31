# Gmail Enhanced MCP — Phase 2 Design Spec

## Overview

Add multi-account support (Gmail + Outlook/M365 + Google Workspace) and Streamable HTTP transport for remote/mobile access via Claude Desktop and Claude mobile app.

**Accounts:**
- `jpastore79@gmail.com` (personal Gmail — existing)
- `jon@degenito.ai` (Microsoft 365 — new)
- Future: additional Gmail/Workspace/Outlook accounts

**Transport:** Dual-mode — stdio (unchanged) + Streamable HTTP (new)
**Deployment target:** Mac Mini with Cloudflare tunnel for mobile access

## Architecture

```
                    ┌─────────────────────────────┐
                    │       Claude Clients         │
                    │  Code (stdio) │ Mobile (HTTP)│
                    └──────┬────────┴──────┬───────┘
                           │               │
                    ┌──────▼───┐    ┌──────▼───────┐
                    │  stdio   │    │  Streamable   │
                    │  server  │    │  HTTP :8420   │
                    └──────┬───┘    └──────┬───────┘
                           │               │
                    ┌──────▼───────────────▼───────┐
                    │       ProtocolHandler         │
                    │       ToolRegistry            │
                    └──────────────┬────────────────┘
                                   │
                    ┌──────────────▼────────────────┐
                    │       AccountRegistry          │
                    │  jpastore79@gmail.com → Gmail  │
                    │  jon@degenito.ai → Outlook     │
                    └───────────────────────────────┘
                           │                │
                    Gmail API v1    Microsoft Graph API
```

### Entry Points

- `python -m gmail_mcp` — stdio mode (Phase 1, unchanged)
- `python -m gmail_mcp serve --port 8420` — Streamable HTTP mode
- `python -m gmail_mcp auth --provider gmail` — Google OAuth2
- `python -m gmail_mcp auth --provider outlook` — Azure AD/MSAL OAuth2

## Project Structure Changes

```
src/
├── email_client.py       # NEW: EmailClient ABC
├── gmail_client.py       # REFACTORED: GmailClient(EmailClient)
├── outlook_client.py     # NEW: OutlookClient(EmailClient)
├── outlook_query.py      # NEW: Gmail search syntax → Graph query translator
├── account_registry.py   # NEW: Maps email → EmailClient instances
├── http_server.py        # NEW: Streamable HTTP transport (FastMCP)
├── auth.py               # EXTENDED: Google + Microsoft auth
├── config.py             # EXTENDED: accounts.json loading
├── main.py               # EXTENDED: serve command
├── server.py             # UNCHANGED
├── protocol.py           # MODIFIED: uses AccountRegistry
├── models.py             # EXTENDED: account param on tools
├── tools/
│   └── __init__.py       # MODIFIED: account routing via AccountRegistry
credentials/
├── jpastore79@gmail.com/
│   └── token.json
├── jon@degenito.ai/
│   └── token.json
└── client_secret.json    # Google OAuth client (shared across Gmail accounts)
accounts.json             # Account registry config
```

## EmailClient Interface

```python
from abc import ABC, abstractmethod
from email.mime.base import MIMEBase
from typing import Any

class EmailClient(ABC):
    @property
    @abstractmethod
    def email_address(self) -> str: ...

    @property
    @abstractmethod
    def provider(self) -> str: ...  # "gmail" or "outlook"

    @abstractmethod
    def get_profile(self) -> dict[str, Any]: ...

    @abstractmethod
    def search_messages(
        self, q: str | None, max_results: int, page_token: str | None,
        include_spam_trash: bool,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def read_message(self, message_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def read_thread(self, thread_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def download_attachment(
        self, message_id: str, attachment_id: str, save_path: str,
    ) -> str: ...

    @abstractmethod
    def list_labels(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def modify_thread_labels(
        self, thread_id: str, add_label_ids: list[str] | None,
        remove_label_ids: list[str] | None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def list_drafts(
        self, max_results: int, page_token: str | None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_draft(
        self, to: str | None, subject: str | None, body: str,
        content_type: str, cc: str | None, bcc: str | None,
        thread_id: str | None, attachments: list[dict[str, Any]] | None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def update_draft(
        self, draft_id: str, to: str | None, subject: str | None,
        body: str, content_type: str, cc: str | None, bcc: str | None,
        attachments: list[dict[str, Any]] | None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def send_draft(self, draft_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def send_email(
        self, to: str, subject: str, body: str, content_type: str,
        cc: str | None, bcc: str | None,
        attachments: list[dict[str, Any]] | None,
    ) -> dict[str, Any]: ...
```

### Return Format Contract

Both clients return normalized dicts. Examples:

**search_messages:** `{"messages": [{"id": "...", "threadId": "..."}], "nextPageToken": "...", "resultSizeEstimate": N}`

**read_message:** Normalized to Gmail-like format with `payload.headers`, `payload.body`, `payload.parts`, `labelIds`, `snippet`, `threadId`.

**list_labels:** `[{"id": "...", "name": "...", "type": "system|user"}]`
- Gmail: labels as-is
- Outlook: folders map to system labels (INBOX→inbox, etc.), categories map to user labels

**create_draft / send_email:** `{"id": "...", "message": {"id": "..."}}`

## AccountRegistry

```python
class AccountRegistry:
    def __init__(self) -> None:
        self._accounts: dict[str, EmailClient] = {}
        self._default: str | None = None

    def register(self, email: str, client: EmailClient) -> None: ...
    def get(self, email: str | None = None) -> EmailClient: ...
    def list_accounts(self) -> list[dict[str, str]]: ...
```

**Configuration (`accounts.json`):**
```json
{
  "default": "jpastore79@gmail.com",
  "accounts": [
    {"email": "jpastore79@gmail.com", "provider": "gmail"},
    {"email": "jon@degenito.ai", "provider": "outlook"}
  ]
}
```

**Credentials stored per-account:** `credentials/{email}/token.json`

## Tool Changes

### New Tool: `list_accounts`
Returns registered accounts with provider type, default indicator.

### All Existing Tools: Add `account` Parameter
```json
{
  "account": {
    "type": "string",
    "description": "Account email (e.g. jon@degenito.ai). Omit for default account."
  }
}
```

Tool handlers route via `registry.get(args.get("account"))`.

**Tool names remain `gmail_*`** — renaming would break existing conversations. The `account` param is what distinguishes.

## Outlook Client — Microsoft Graph Integration

### Authentication

- Azure AD app registration in degenito.ai tenant
- MSAL Python library (`msal>=1.28.0`)
- Delegated permissions: `Mail.ReadWrite`, `Mail.Send`, `User.Read`
- Token cache: MSAL's `SerializableTokenCache` persisted to `credentials/{email}/token.json`
- Auth flow: `python -m gmail_mcp auth --provider outlook` opens browser for Azure AD consent

### Graph API Mapping

| EmailClient method | Graph API endpoint |
|---|---|
| `get_profile()` | `GET /me` |
| `search_messages(q)` | Hybrid: `$filter` + `$search` (see query translation) |
| `read_message(id)` | `GET /me/messages/{id}` |
| `read_thread(id)` | `GET /me/messages?$filter=conversationId eq '{id}'` |
| `download_attachment(msg, att)` | `GET /me/messages/{msg}/attachments/{att}/$value` |
| `list_labels()` | `GET /me/mailFolders` + `GET /me/outlook/masterCategories` |
| `modify_thread_labels()` | `PATCH /me/messages/{id}` (move folder / set categories) |
| `create_draft()` | `POST /me/messages` with `isDraft` implicit + attachments |
| `update_draft()` | `PATCH /me/messages/{id}` |
| `send_draft()` | `POST /me/messages/{id}/send` |
| `send_email()` | `POST /me/sendMail` with inline attachments |
| `list_drafts()` | `GET /me/mailFolders/drafts/messages` |

### Attachment Handling

- Files <3MB: inline JSON with base64 `contentBytes` in the message body
- Files 3-150MB: upload session via `POST /me/messages/{id}/attachments/createUploadSession`, then chunked PUT
- Download: `GET /me/messages/{msg}/attachments/{att}/$value` returns raw bytes
- Graph also supports raw MIME via `Content-Type: text/plain` body

### Search Query Translation (`outlook_query.py`)

Hybrid approach — parse Gmail syntax and route operators appropriately:

| Gmail Operator | Graph Mechanism | Translation |
|---|---|---|
| `from:x@y.com` | `$search` KQL | `from:x@y.com` |
| `to:x@y.com` | `$search` KQL | `to:x@y.com` |
| `subject:word` | `$search` KQL | `subject:word` |
| `is:unread` | `$filter` | `isRead eq false` |
| `is:read` | `$filter` | `isRead eq true` |
| `is:starred` | `$filter` | `flag/flagStatus eq 'flagged'` |
| `has:attachment` | `$filter` | `hasAttachments eq true` |
| `label:name` | `$filter` | `categories/any(c:c eq 'name')` |
| `after:YYYY/M/D` | `$filter` | `receivedDateTime ge YYYY-MM-DDT00:00:00Z` |
| `before:YYYY/M/D` | `$filter` | `receivedDateTime lt YYYY-MM-DDT00:00:00Z` |
| `newer_than:Nd` | `$filter` | Compute date, `receivedDateTime ge {computed}` |
| `in:inbox` | Endpoint path | `/me/mailFolders/inbox/messages` |
| `in:sent` | Endpoint path | `/me/mailFolders/sentitems/messages` |
| `in:drafts` | Endpoint path | `/me/mailFolders/drafts/messages` |
| `in:trash` | Endpoint path | `/me/mailFolders/deleteditems/messages` |
| `"exact phrase"` | `$search` KQL | `"exact phrase"` |
| `OR` | `$search` KQL | `OR` (uppercase) |
| `-from:x` | `$search` KQL | `NOT from:x` |

**Key constraint:** `$search` and `$filter` are mutually exclusive on the messages endpoint. When a query contains both KQL-routed and filter-routed operators, `OutlookClient` will:
1. Use `$filter` for the filterable operators
2. Apply KQL operators as a post-filter on the client side (for simple text matching)
3. Or split into two API calls and intersect results (for complex queries)

Unsupported syntax falls back to `$search` with the raw string.

## Streamable HTTP Transport

### Protocol (MCP spec 2025-03-26)

Single endpoint: `/mcp` (configurable)

| Method | Purpose |
|--------|---------|
| POST `/mcp` | JSON-RPC requests from client |
| GET `/mcp` | SSE stream for server-initiated messages |
| DELETE `/mcp` | Terminate session |

Session tracked via `Mcp-Session-Id` HTTP header (assigned on `initialize` response, required on all subsequent requests).

### Implementation (`src/http_server.py`)

Uses the MCP Python SDK's `FastMCP` with `streamable_http_app()`:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gmail-enhanced-mcp")
# Register all tools on mcp
app = mcp.streamable_http_app()  # Returns Starlette ASGI app
```

Wrapped in a middleware layer for:
- Bearer token auth (`MCP_AUTH_TOKEN` env var, required)
- CORS headers (for potential web clients)
- Health check endpoint at `/health`

### Auth

Bearer token via `Authorization: Bearer {token}` header on all requests. Token set via `MCP_AUTH_TOKEN` environment variable. Health endpoint (`/health`) is unauthenticated.

### Claude Desktop Config

```json
{
  "mcpServers": {
    "gmail-enhanced": {
      "url": "http://localhost:8420/mcp",
      "headers": {
        "Authorization": "Bearer ${MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

### Cloudflare Tunnel (Mobile Access)

```bash
cloudflared tunnel --url http://localhost:8420 --hostname gmail-mcp.degenito.ai
```

Claude mobile app connects to `https://gmail-mcp.degenito.ai/mcp` with bearer token.

## Mac Mini Deployment

A `DEPLOY.md` will document:

1. **Prerequisites**: Python 3.11+, pip, cloudflared
2. **Clone and install**: `git clone`, `pip install -r requirements.txt`
3. **Auth setup**: Run `python -m gmail_mcp auth --provider gmail` and `--provider outlook` for each account
4. **Configure accounts.json**: List all accounts with defaults
5. **Set environment**: `.env` with `MCP_AUTH_TOKEN`, `LOG_LEVEL`, etc.
6. **Claude Desktop integration**: Copy config to Claude Desktop's MCP settings
7. **Launch as service**: `launchd` plist for auto-start on boot (`~/Library/LaunchAgents/com.gmail-mcp.plist`)
8. **Cloudflare tunnel**: `cloudflared` service for persistent tunnel
9. **Mobile setup**: Add remote MCP URL in Claude mobile app

## Dependencies — New

```
msal>=1.28.0          # Microsoft auth
mcp>=1.0.0            # MCP Python SDK (FastMCP, Streamable HTTP)
uvicorn>=0.30.0       # ASGI server for HTTP mode
starlette>=0.38.0     # Required by MCP SDK
httpx>=0.27.0         # Required by MCP SDK
```

## Testing Strategy

- **Unit tests**: Mock Graph API responses, test OutlookClient in isolation
- **Unit tests**: Test query translator with all Gmail syntax patterns
- **Unit tests**: Test AccountRegistry routing
- **Integration tests**: Streamable HTTP roundtrip with mocked clients
- **Integration tests**: Multi-account tool calls routing correctly
- **Live tests**: `@pytest.mark.live` for real API calls (both providers)
- **Coverage**: 90%+ for new code

## Safety Rails — New

1. NEVER send from the wrong account — always confirm account param matches intent
2. NEVER store Azure AD tokens outside `credentials/` directory
3. NEVER log Microsoft Graph API tokens or response bodies
4. Bearer token for HTTP mode is REQUIRED — server refuses to start without it
5. Cloudflare tunnel MUST use HTTPS (enforced by Cloudflare)
