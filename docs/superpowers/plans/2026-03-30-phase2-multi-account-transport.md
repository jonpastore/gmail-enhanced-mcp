# Phase 2: Multi-Account + Streamable HTTP Transport — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-account support (Gmail + Outlook/M365) with unified EmailClient interface, and Streamable HTTP transport for remote/mobile access.

**Architecture:** Extract EmailClient ABC from GmailClient, add OutlookClient via Microsoft Graph, AccountRegistry routes tool calls by `account` param. Streamable HTTP via MCP SDK's `Server` + `StreamableHTTPSessionManager` with bearer token auth middleware. Dual-mode: stdio (unchanged) + HTTP.

**Tech Stack:** Python 3.11+, msal, mcp SDK, uvicorn, starlette, Microsoft Graph API, existing google-api-python-client

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/email_client.py` | CREATE | EmailClient ABC |
| `src/gmail_client.py` | MODIFY | GmailClient(EmailClient), move shared attachment helpers to base |
| `src/outlook_client.py` | CREATE | OutlookClient(EmailClient) via Microsoft Graph |
| `src/outlook_query.py` | CREATE | Gmail search syntax → Graph $filter/$search translator |
| `src/account_registry.py` | CREATE | Maps email → EmailClient, loads accounts.json |
| `src/auth.py` | MODIFY | Add Microsoft auth (MSAL) alongside Google OAuth |
| `src/config.py` | MODIFY | Add accounts.json path, MCP_AUTH_TOKEN |
| `src/main.py` | MODIFY | Add `serve` and `auth --provider` commands |
| `src/http_server.py` | CREATE | Streamable HTTP transport with auth middleware |
| `src/protocol.py` | MODIFY | Use AccountRegistry instead of direct GmailClient |
| `src/tools/__init__.py` | MODIFY | Add `account` param to all tools, add `list_accounts` tool |
| `accounts.json` | CREATE | Account configuration |
| `DEPLOY.md` | CREATE | Mac Mini deployment instructions |
| `requirements.txt` | MODIFY | Add msal, mcp, uvicorn, starlette, httpx |
| `tests/unit/test_email_client.py` | CREATE | ABC contract tests |
| `tests/unit/test_outlook_client.py` | CREATE | OutlookClient unit tests |
| `tests/unit/test_outlook_query.py` | CREATE | Query translator tests |
| `tests/unit/test_account_registry.py` | CREATE | Registry routing tests |
| `tests/unit/test_auth_microsoft.py` | CREATE | MSAL auth tests |
| `tests/integration/test_http_server.py` | CREATE | Streamable HTTP roundtrip tests |
| `tests/integration/test_multi_account.py` | CREATE | Multi-account tool routing tests |

---

### Task 1: EmailClient ABC + GmailClient Refactor

**Files:**
- Create: `src/email_client.py`
- Modify: `src/gmail_client.py`
- Create: `tests/unit/test_email_client.py`

- [ ] **Step 1: Write test verifying GmailClient implements EmailClient**

Create `tests/unit/test_email_client.py`:

```python
from __future__ import annotations

from src.email_client import EmailClient
from src.gmail_client import GmailClient


class TestEmailClientInterface:
    def test_gmail_client_is_email_client(self) -> None:
        assert issubclass(GmailClient, EmailClient)

    def test_email_client_has_required_methods(self) -> None:
        methods = [
            "get_profile", "search_messages", "read_message", "read_thread",
            "download_attachment", "list_labels", "modify_thread_labels",
            "list_drafts", "create_draft", "update_draft", "send_draft",
            "send_email", "build_mime_message",
        ]
        for method in methods:
            assert hasattr(EmailClient, method), f"Missing method: {method}"

    def test_email_client_has_properties(self) -> None:
        assert hasattr(EmailClient, "email_address")
        assert hasattr(EmailClient, "provider")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/test_email_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.email_client'`

- [ ] **Step 3: Create EmailClient ABC**

Create `src/email_client.py`:

```python
from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from email.mime.application import MIMEApplication
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests
from loguru import logger

BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".scr", ".js", ".vbs", ".msi"}
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024


class EmailClient(ABC):
    @property
    @abstractmethod
    def email_address(self) -> str: ...

    @property
    @abstractmethod
    def provider(self) -> str: ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]: ...

    @abstractmethod
    def search_messages(
        self,
        q: str | None = None,
        max_results: int = 20,
        page_token: str | None = None,
        include_spam_trash: bool = False,
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
        self,
        thread_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def list_drafts(
        self, max_results: int = 20, page_token: str | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_draft(
        self,
        to: str | None = None,
        subject: str | None = None,
        body: str = "",
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        thread_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def update_draft(
        self,
        draft_id: str,
        to: str | None = None,
        subject: str | None = None,
        body: str = "",
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def send_draft(self, draft_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def build_mime_message(
        self,
        to: str | None = None,
        subject: str | None = None,
        body: str = "",
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        thread_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> MIMEBase:
        msg: MIMEBase
        if attachments:
            multi = MIMEMultipart("mixed")
            text_part = MIMEText(body, "html" if content_type == "text/html" else "plain")
            multi.attach(text_part)
            for att in attachments:
                att_part = self._resolve_attachment(att)
                multi.attach(att_part)
            msg = multi
        else:
            subtype = "html" if content_type == "text/html" else "plain"
            msg = MIMEText(body, subtype)
        if to:
            msg["To"] = to
        if subject:
            msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        return msg

    def _resolve_attachment(self, att: dict[str, Any]) -> MIMEBase:
        att_type = att["type"]
        if att_type == "file":
            return self._resolve_file_attachment(att["path"])
        elif att_type == "url":
            return self._resolve_url_attachment(att["url"], att["filename"])
        elif att_type == "gmail":
            return self._resolve_provider_attachment(att)
        else:
            raise ValueError(f"Unknown attachment type: {att_type}")

    def _resolve_provider_attachment(self, att: dict[str, Any]) -> MIMEBase:
        raise NotImplementedError("Subclass must implement provider-specific attachment resolution")

    def _resolve_file_attachment(self, file_path: str) -> MIMEBase:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Attachment path does not exist: {file_path}")
        if path.suffix.lower() in BLOCKED_EXTENSIONS:
            raise ValueError(f"Blocked attachment type: {path.suffix}")
        data = path.read_bytes()
        if len(data) > MAX_ATTACHMENT_SIZE:
            size_mb = len(data) / (1024 * 1024)
            raise ValueError(f"Attachment exceeds 25MB limit: {path.name} ({size_mb:.1f}MB)")
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)
        part: MIMEBase
        if maintype == "image":
            part = MIMEImage(data, _subtype=subtype)
        elif maintype == "audio":
            part = MIMEAudio(data, _subtype=subtype)
        elif maintype == "application":
            part = MIMEApplication(data, _subtype=subtype)
        else:
            part = MIMEBase(maintype, subtype)
            part.set_payload(data)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        return part

    def _resolve_url_attachment(self, url: str, filename: str) -> MIMEBase:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.content
        if len(data) > MAX_ATTACHMENT_SIZE:
            size_mb = len(data) / (1024 * 1024)
            raise ValueError(f"URL attachment exceeds 25MB limit: {filename} ({size_mb:.1f}MB)")
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        subtype = content_type.split("/")[1].split(";")[0] if "/" in content_type else "octet-stream"
        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        return part
```

- [ ] **Step 4: Refactor GmailClient to extend EmailClient**

Modify `src/gmail_client.py` — remove duplicated attachment helpers (now in base class), add `email_address` and `provider` properties, extend `EmailClient`, override `_resolve_provider_attachment` for Gmail-specific attachment fetching:

```python
from __future__ import annotations

import base64
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from typing import Any

from googleapiclient.discovery import build
from loguru import logger

from .auth import TokenManager
from .email_client import EmailClient


class GmailClient(EmailClient):
    def __init__(self, token_manager: TokenManager, account_email: str) -> None:
        self._token_mgr = token_manager
        self._account_email = account_email
        self._service: Any = None

    @property
    def email_address(self) -> str:
        return self._account_email

    @property
    def provider(self) -> str:
        return "gmail"

    def _get_service(self) -> Any:
        if self._service is None:
            creds = self._token_mgr.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    # All existing methods stay the same (get_profile, search_messages, etc.)
    # Remove: build_mime_message, _resolve_attachment, _resolve_file_attachment,
    #         _resolve_url_attachment (now inherited from EmailClient)
    # Keep: _resolve_gmail_attachment renamed to _resolve_provider_attachment
    # Keep: _find_attachment_filename, _encode_message

    def _resolve_provider_attachment(self, att: dict[str, Any]) -> MIMEBase:
        svc = self._get_service()
        att_data = (
            svc.users().messages().attachments()
            .get(userId="me", messageId=att["message_id"], id=att["attachment_id"])
            .execute()
        )
        data = base64.urlsafe_b64decode(att_data["data"])
        msg = svc.users().messages().get(
            userId="me", id=att["message_id"], format="full"
        ).execute()
        filename = self._find_attachment_filename(msg, att["attachment_id"])
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename) if filename else (None, None)
        mime_type = mime_type or "application/octet-stream"
        _maintype, subtype = mime_type.split("/", 1)
        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename or "attachment")
        return part
```

**Important:** The constructor changes from `GmailClient(config)` to `GmailClient(token_manager, account_email)`. Update all call sites (protocol.py, tests).

- [ ] **Step 5: Run all existing tests to verify refactor didn't break anything**

```bash
python -m pytest tests/ -v
```

Expected: All 75 tests PASS (some may need constructor updates in mocks)

- [ ] **Step 6: Fix any broken tests due to constructor change**

Update `tests/unit/test_gmail_client.py` — the `_make_client` helper needs to set `_account_email`:
```python
def _make_client(mock_service: MagicMock | None = None) -> GmailClient:
    client = GmailClient.__new__(GmailClient)
    client._service = mock_service or MagicMock()
    client._account_email = "test@gmail.com"
    return client
```

Update `tests/unit/test_protocol.py` and `tests/integration/test_stdio_roundtrip.py` — patch paths change since `ProtocolHandler.__init__` will be updated in Task 5.

- [ ] **Step 7: Run tests again**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/email_client.py src/gmail_client.py tests/unit/test_email_client.py tests/unit/test_gmail_client.py
git commit -m "refactor: extract EmailClient ABC, GmailClient extends it"
```

---

### Task 2: AccountRegistry

**Files:**
- Create: `src/account_registry.py`
- Create: `tests/unit/test_account_registry.py`

- [ ] **Step 1: Write AccountRegistry tests**

Create `tests/unit/test_account_registry.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.account_registry import AccountRegistry


def _mock_client(email: str, provider: str) -> MagicMock:
    client = MagicMock()
    client.email_address = email
    client.provider = provider
    return client


class TestAccountRegistry:
    def test_register_and_get(self) -> None:
        reg = AccountRegistry()
        client = _mock_client("test@gmail.com", "gmail")
        reg.register("test@gmail.com", client)
        assert reg.get("test@gmail.com") is client

    def test_get_default(self) -> None:
        reg = AccountRegistry()
        client = _mock_client("test@gmail.com", "gmail")
        reg.register("test@gmail.com", client, default=True)
        assert reg.get() is client

    def test_first_registered_is_default(self) -> None:
        reg = AccountRegistry()
        c1 = _mock_client("a@gmail.com", "gmail")
        c2 = _mock_client("b@outlook.com", "outlook")
        reg.register("a@gmail.com", c1)
        reg.register("b@outlook.com", c2)
        assert reg.get() is c1

    def test_get_unknown_raises(self) -> None:
        reg = AccountRegistry()
        with pytest.raises(ValueError, match="Unknown account"):
            reg.get("nonexistent@test.com")

    def test_get_no_accounts_raises(self) -> None:
        reg = AccountRegistry()
        with pytest.raises(ValueError, match="No accounts registered"):
            reg.get()

    def test_list_accounts(self) -> None:
        reg = AccountRegistry()
        reg.register("a@gmail.com", _mock_client("a@gmail.com", "gmail"))
        reg.register("b@outlook.com", _mock_client("b@outlook.com", "outlook"))
        accounts = reg.list_accounts()
        assert len(accounts) == 2
        assert accounts[0]["email"] == "a@gmail.com"
        assert accounts[0]["provider"] == "gmail"
        assert accounts[0]["default"] is True
        assert accounts[1]["default"] is False

    def test_multiple_gmail_accounts(self) -> None:
        reg = AccountRegistry()
        reg.register("personal@gmail.com", _mock_client("personal@gmail.com", "gmail"))
        reg.register("work@company.com", _mock_client("work@company.com", "gmail"))
        assert reg.get("work@company.com").email_address == "work@company.com"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/test_account_registry.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement AccountRegistry**

Create `src/account_registry.py`:

```python
from __future__ import annotations

from typing import Any

from .email_client import EmailClient


class AccountRegistry:
    def __init__(self) -> None:
        self._accounts: dict[str, EmailClient] = {}
        self._default: str | None = None

    def register(self, email: str, client: EmailClient, default: bool = False) -> None:
        self._accounts[email] = client
        if default or self._default is None:
            self._default = email

    def get(self, email: str | None = None) -> EmailClient:
        if email is not None:
            client = self._accounts.get(email)
            if client is None:
                available = ", ".join(self._accounts.keys()) or "none"
                raise ValueError(f"Unknown account: {email}. Available: {available}")
            return client
        if self._default is None:
            raise ValueError("No accounts registered")
        return self._accounts[self._default]

    def list_accounts(self) -> list[dict[str, Any]]:
        result = []
        for email, client in self._accounts.items():
            result.append({
                "email": email,
                "provider": client.provider,
                "default": email == self._default,
            })
        return result
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/unit/test_account_registry.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/account_registry.py tests/unit/test_account_registry.py
git commit -m "feat: AccountRegistry for multi-account routing"
```

---

### Task 3: Tool Registry — Add `account` Param + `list_accounts` Tool

**Files:**
- Modify: `src/tools/__init__.py`
- Modify: `src/protocol.py`
- Create: `tests/integration/test_multi_account.py`

- [ ] **Step 1: Write multi-account routing test**

Create `tests/integration/test_multi_account.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from src.account_registry import AccountRegistry
from src.models import ToolCallParams
from src.tools import ToolRegistry


def _mock_client(email: str, provider: str) -> MagicMock:
    client = MagicMock()
    client.email_address = email
    client.provider = provider
    client.get_profile.return_value = {"emailAddress": email}
    return client


class TestMultiAccountRouting:
    def test_default_account_used_when_no_account_param(self) -> None:
        reg = AccountRegistry()
        gmail = _mock_client("personal@gmail.com", "gmail")
        reg.register("personal@gmail.com", gmail)
        registry = ToolRegistry(account_registry=reg)
        registry.execute_tool(ToolCallParams(name="gmail_get_profile", arguments={}))
        gmail.get_profile.assert_called_once()

    def test_explicit_account_routes_correctly(self) -> None:
        reg = AccountRegistry()
        gmail = _mock_client("personal@gmail.com", "gmail")
        outlook = _mock_client("work@company.com", "outlook")
        reg.register("personal@gmail.com", gmail)
        reg.register("work@company.com", outlook)
        registry = ToolRegistry(account_registry=reg)
        registry.execute_tool(ToolCallParams(
            name="gmail_get_profile",
            arguments={"account": "work@company.com"},
        ))
        outlook.get_profile.assert_called_once()
        gmail.get_profile.assert_not_called()

    def test_list_accounts_tool(self) -> None:
        reg = AccountRegistry()
        reg.register("a@gmail.com", _mock_client("a@gmail.com", "gmail"))
        reg.register("b@outlook.com", _mock_client("b@outlook.com", "outlook"))
        registry = ToolRegistry(account_registry=reg)
        result = registry.execute_tool(ToolCallParams(
            name="gmail_list_accounts", arguments={},
        ))
        text = result["content"][0]["text"]
        assert "a@gmail.com" in text
        assert "b@outlook.com" in text

    def test_account_param_in_tool_schemas(self) -> None:
        reg = AccountRegistry()
        reg.register("a@gmail.com", _mock_client("a@gmail.com", "gmail"))
        registry = ToolRegistry(account_registry=reg)
        tools = registry.list_tools()
        for tool in tools:
            if tool["name"] != "gmail_list_accounts":
                props = tool["inputSchema"].get("properties", {})
                assert "account" in props, f"{tool['name']} missing account param"
```

- [ ] **Step 2: Update ToolRegistry to accept AccountRegistry and route by account**

Modify `src/tools/__init__.py`:
- Change constructor from `gmail_client` to `account_registry`
- Add `account` property to all TOOL_DEFINITIONS inputSchemas
- Add `gmail_list_accounts` tool definition and handler
- In `execute_tool`, extract `account` from args, call `registry.get(account)` to get the right client, pass client to handler

Key changes to `execute_tool`:
```python
def execute_tool(self, params: ToolCallParams) -> dict[str, Any]:
    handler = self._handlers.get(params.name)
    if handler is None:
        raise ValueError(f"Unknown tool: {params.name}")
    logger.info(f"Executing tool: {params.name}")
    if params.name == "gmail_list_accounts":
        return handler(params.arguments, self._registry)
    account = params.arguments.pop("account", None)
    client = self._registry.get(account)
    return handler(params.arguments, client)
```

- [ ] **Step 3: Update ProtocolHandler to use AccountRegistry**

Modify `src/protocol.py` `__init__`:
```python
def __init__(self) -> None:
    from .account_registry import AccountRegistry
    from .config import Config

    cfg = Config()
    registry = AccountRegistry()
    registry.load_from_config(cfg)  # loads accounts.json, creates clients
    self.tool_registry = ToolRegistry(account_registry=registry)
    self.initialized = False
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS (existing tests need mock updates for new constructor)

- [ ] **Step 5: Commit**

```bash
git add src/tools/__init__.py src/protocol.py tests/integration/test_multi_account.py
git commit -m "feat: multi-account tool routing with account param"
```

---

### Task 4: Microsoft Auth (MSAL)

**Files:**
- Modify: `src/auth.py`
- Create: `tests/unit/test_auth_microsoft.py`

- [ ] **Step 1: Write Microsoft auth tests**

Create `tests/unit/test_auth_microsoft.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.auth import MicrosoftTokenManager


class TestMicrosoftTokenManager:
    def test_load_cache_from_file(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "token.json"
        cache_file.write_text('{"AccessToken": {}}')
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(cache_file),
        )
        assert mgr._load_cache() is not None

    def test_load_cache_returns_empty_when_missing(self, tmp_path: Path) -> None:
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(tmp_path / "nonexistent.json"),
        )
        cache = mgr._load_cache()
        assert cache is not None  # returns empty cache, not None

    def test_get_token_raises_when_no_accounts(self, tmp_path: Path) -> None:
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(tmp_path / "token.json"),
        )
        with pytest.raises(RuntimeError, match="Not authenticated"):
            mgr.get_token()

    def test_save_cache_writes_file(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "token.json"
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(cache_file),
        )
        with patch("src.auth.msal") as mock_msal:
            mock_cache = MagicMock()
            mock_cache.serialize.return_value = '{"cached": true}'
            mock_cache.has_state_changed = True
            mgr._cache = mock_cache
            mgr._save_cache()
            assert cache_file.exists()
            assert json.loads(cache_file.read_text()) == {"cached": True}
```

- [ ] **Step 2: Implement MicrosoftTokenManager in auth.py**

Add to `src/auth.py`:

```python
import msal

MICROSOFT_SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
]


class MicrosoftTokenManager:
    def __init__(self, client_id: str, tenant_id: str, token_path: str) -> None:
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._token_path = Path(token_path)
        self._cache: msal.SerializableTokenCache | None = None
        self._app: msal.PublicClientApplication | None = None

    def _load_cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if self._token_path.exists():
            cache.deserialize(self._token_path.read_text())
        return cache

    def _save_cache(self) -> None:
        if self._cache and self._cache.has_state_changed:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(self._cache.serialize())

    def _get_app(self) -> msal.PublicClientApplication:
        if self._app is None:
            self._cache = self._load_cache()
            self._app = msal.PublicClientApplication(
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                token_cache=self._cache,
            )
        return self._app

    def get_token(self) -> str:
        app = self._get_app()
        accounts = app.get_accounts()
        if not accounts:
            raise RuntimeError(
                "Not authenticated. Run: python -m gmail_mcp auth --provider outlook"
            )
        result = app.acquire_token_silent(MICROSOFT_SCOPES, account=accounts[0])
        if not result or "access_token" not in result:
            raise RuntimeError(
                "Token expired and cannot refresh. Run: python -m gmail_mcp auth --provider outlook"
            )
        self._save_cache()
        return result["access_token"]

    def run_interactive_auth(self) -> None:
        app = self._get_app()
        result = app.acquire_token_interactive(MICROSOFT_SCOPES)
        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "Unknown"))
            raise RuntimeError(f"Authentication failed: {error}")
        self._save_cache()
        logger.info("Microsoft auth successful")
```

Also update `run_auth_flow` to accept `--provider` param:

```python
def run_auth_flow(cfg: Config, provider: str = "gmail") -> None:
    if provider == "gmail":
        # existing Google OAuth flow
        ...
    elif provider == "outlook":
        ms_cfg = cfg.get_microsoft_config()
        mgr = MicrosoftTokenManager(
            client_id=ms_cfg["client_id"],
            tenant_id=ms_cfg["tenant_id"],
            token_path=ms_cfg["token_path"],
        )
        mgr.run_interactive_auth()
        print("Microsoft authentication successful! Token saved.")
    else:
        print(f"Unknown provider: {provider}")
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/unit/test_auth_microsoft.py tests/unit/test_auth.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/auth.py tests/unit/test_auth_microsoft.py
git commit -m "feat: Microsoft MSAL auth for Outlook/M365 accounts"
```

---

### Task 5: Outlook Query Translator

**Files:**
- Create: `src/outlook_query.py`
- Create: `tests/unit/test_outlook_query.py`

- [ ] **Step 1: Write query translator tests**

Create `tests/unit/test_outlook_query.py`:

```python
from __future__ import annotations

from src.outlook_query import translate_gmail_query, QueryParts


class TestTranslateGmailQuery:
    def test_from_operator(self) -> None:
        result = translate_gmail_query("from:user@example.com")
        assert result.search == "from:user@example.com"

    def test_subject_operator(self) -> None:
        result = translate_gmail_query("subject:meeting")
        assert result.search == "subject:meeting"

    def test_is_unread(self) -> None:
        result = translate_gmail_query("is:unread")
        assert "isRead eq false" in result.filter

    def test_is_starred(self) -> None:
        result = translate_gmail_query("is:starred")
        assert "flagStatus eq 'flagged'" in result.filter

    def test_has_attachment(self) -> None:
        result = translate_gmail_query("has:attachment")
        assert "hasAttachments eq true" in result.filter

    def test_after_date(self) -> None:
        result = translate_gmail_query("after:2024/1/15")
        assert "receivedDateTime ge 2024-01-15" in result.filter

    def test_before_date(self) -> None:
        result = translate_gmail_query("before:2024/12/31")
        assert "receivedDateTime lt 2024-12-31" in result.filter

    def test_in_inbox(self) -> None:
        result = translate_gmail_query("in:inbox")
        assert result.folder == "inbox"

    def test_in_sent(self) -> None:
        result = translate_gmail_query("in:sent")
        assert result.folder == "sentitems"

    def test_in_drafts(self) -> None:
        result = translate_gmail_query("in:drafts")
        assert result.folder == "drafts"

    def test_in_trash(self) -> None:
        result = translate_gmail_query("in:trash")
        assert result.folder == "deleteditems"

    def test_label_becomes_category(self) -> None:
        result = translate_gmail_query("label:Travel")
        assert "categories/any" in result.filter
        assert "Travel" in result.filter

    def test_newer_than_days(self) -> None:
        result = translate_gmail_query("newer_than:7d")
        assert "receivedDateTime ge" in result.filter

    def test_mixed_search_and_filter(self) -> None:
        result = translate_gmail_query("from:boss@company.com is:unread has:attachment")
        assert result.search == "from:boss@company.com"
        assert "isRead eq false" in result.filter
        assert "hasAttachments eq true" in result.filter

    def test_exact_phrase(self) -> None:
        result = translate_gmail_query('"exact phrase"')
        assert '"exact phrase"' in result.search

    def test_negation(self) -> None:
        result = translate_gmail_query("-from:noreply@example.com")
        assert "NOT from:noreply@example.com" in result.search

    def test_or_operator(self) -> None:
        result = translate_gmail_query("from:alice OR from:bob")
        assert "from:alice OR from:bob" in result.search

    def test_plain_text_search(self) -> None:
        result = translate_gmail_query("hello world")
        assert result.search == "hello world"
        assert result.filter == ""
        assert result.folder is None

    def test_empty_query(self) -> None:
        result = translate_gmail_query(None)
        assert result.search == ""
        assert result.filter == ""
        assert result.folder is None
```

- [ ] **Step 2: Implement query translator**

Create `src/outlook_query.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class QueryParts:
    search: str = ""
    filter: str = ""
    folder: str | None = None


FOLDER_MAP = {
    "inbox": "inbox",
    "sent": "sentitems",
    "drafts": "drafts",
    "trash": "deleteditems",
    "spam": "junkemail",
    "junk": "junkemail",
}

FILTER_OPERATORS = {
    "is:unread": "isRead eq false",
    "is:read": "isRead eq true",
    "is:starred": "flag/flagStatus eq 'flagged'",
    "has:attachment": "hasAttachments eq true",
}


def translate_gmail_query(q: str | None) -> QueryParts:
    if not q:
        return QueryParts()

    parts = QueryParts()
    filters: list[str] = []
    search_parts: list[str] = []
    tokens = _tokenize(q)

    for token in tokens:
        if token in FILTER_OPERATORS:
            filters.append(FILTER_OPERATORS[token])
        elif token.startswith("in:"):
            folder_name = token[3:]
            parts.folder = FOLDER_MAP.get(folder_name, folder_name)
        elif token.startswith("after:"):
            date_str = _parse_date(token[6:])
            filters.append(f"receivedDateTime ge {date_str}T00:00:00Z")
        elif token.startswith("before:"):
            date_str = _parse_date(token[7:])
            filters.append(f"receivedDateTime lt {date_str}T00:00:00Z")
        elif token.startswith("newer_than:"):
            days = _parse_relative_date(token[11:])
            dt = datetime.now(timezone.utc) - timedelta(days=days)
            filters.append(f"receivedDateTime ge {dt.strftime('%Y-%m-%d')}T00:00:00Z")
        elif token.startswith("label:"):
            label = token[6:]
            filters.append(f"categories/any(c:c eq '{label}')")
        elif token.startswith("-"):
            search_parts.append(f"NOT {token[1:]}")
        else:
            search_parts.append(token)

    parts.search = " ".join(search_parts)
    parts.filter = " and ".join(filters)
    return parts


def _tokenize(q: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(q):
        if q[i] == '"':
            end = q.index('"', i + 1) if '"' in q[i + 1:] else len(q)
            tokens.append(q[i:end + 1])
            i = end + 1
        elif q[i] == ' ':
            i += 1
        else:
            end = q.index(' ', i) if ' ' in q[i:] else len(q)
            tokens.append(q[i:end])
            i = end
    return tokens


def _parse_date(date_str: str) -> str:
    parts = date_str.replace("-", "/").split("/")
    if len(parts) == 3:
        year, month, day = parts[0], parts[1].zfill(2), parts[2].zfill(2)
        return f"{year}-{month}-{day}"
    return date_str


def _parse_relative_date(spec: str) -> int:
    match = re.match(r"(\d+)([dhm])", spec)
    if not match:
        return 7
    value, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return value
    elif unit == "h":
        return max(1, value // 24)
    elif unit == "m":
        return value * 30
    return value
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/unit/test_outlook_query.py -v
```

Expected: All 19 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/outlook_query.py tests/unit/test_outlook_query.py
git commit -m "feat: Gmail search syntax to Microsoft Graph query translator"
```

---

### Task 6: OutlookClient

**Files:**
- Create: `src/outlook_client.py`
- Create: `tests/unit/test_outlook_client.py`

- [ ] **Step 1: Write OutlookClient tests**

Create `tests/unit/test_outlook_client.py`:

```python
from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.outlook_client import OutlookClient


def _make_client(mock_get: MagicMock | None = None, mock_post: MagicMock | None = None) -> OutlookClient:
    client = OutlookClient.__new__(OutlookClient)
    client._token_mgr = MagicMock()
    client._token_mgr.get_token.return_value = "test_token"
    client._account_email = "jon@degenito.ai"
    client._mock_get = mock_get
    client._mock_post = mock_post
    return client


class TestGetProfile:
    def test_returns_normalized_profile(self) -> None:
        with patch("src.outlook_client.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "mail": "jon@degenito.ai",
                "displayName": "Jon Pastore",
            }
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            client = _make_client()
            result = client.get_profile()
            assert result["emailAddress"] == "jon@degenito.ai"


class TestSearchMessages:
    def test_returns_normalized_results(self) -> None:
        with patch("src.outlook_client.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "value": [
                    {"id": "msg1", "conversationId": "conv1"},
                ],
                "@odata.count": 1,
            }
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            client = _make_client()
            result = client.search_messages(q="from:test@example.com")
            assert len(result["messages"]) == 1
            assert result["messages"][0]["id"] == "msg1"
            assert result["messages"][0]["threadId"] == "conv1"


class TestReadMessage:
    def test_returns_normalized_message(self) -> None:
        with patch("src.outlook_client.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "id": "msg1",
                "conversationId": "conv1",
                "subject": "Test",
                "from": {"emailAddress": {"name": "Sender", "address": "sender@test.com"}},
                "toRecipients": [{"emailAddress": {"address": "jon@degenito.ai"}}],
                "body": {"contentType": "text", "content": "Hello"},
                "receivedDateTime": "2026-03-01T10:00:00Z",
                "isRead": False,
                "hasAttachments": False,
            }
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            client = _make_client()
            result = client.read_message("msg1")
            assert result["id"] == "msg1"
            assert result["threadId"] == "conv1"
            headers = result["payload"]["headers"]
            from_header = next(h for h in headers if h["name"] == "From")
            assert "sender@test.com" in from_header["value"]


class TestCreateDraft:
    def test_creates_draft_returns_id(self) -> None:
        with patch("src.outlook_client.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "draft1"}
            mock_resp.raise_for_status = MagicMock()
            mock_req.post.return_value = mock_resp
            client = _make_client()
            result = client.create_draft(
                to="test@example.com", subject="Test", body="Hello",
            )
            assert result["id"] == "draft1"


class TestSendEmail:
    def test_sends_email(self) -> None:
        with patch("src.outlook_client.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_resp.raise_for_status = MagicMock()
            mock_req.post.return_value = mock_resp
            client = _make_client()
            result = client.send_email(
                to="test@example.com", subject="Test", body="Hello",
            )
            assert result["id"]  # returns a generated confirmation


class TestOutlookIsEmailClient:
    def test_implements_interface(self) -> None:
        from src.email_client import EmailClient
        assert issubclass(OutlookClient, EmailClient)
```

- [ ] **Step 2: Implement OutlookClient**

Create `src/outlook_client.py` — full implementation using Microsoft Graph API. This is the largest file in the task. Key methods:

- `_graph_request(method, path, **kwargs)` — centralized Graph API caller with auth header
- `get_profile()` → `GET /me` → normalize to `{"emailAddress": ..., "messagesTotal": ...}`
- `search_messages(q)` → use `outlook_query.translate_gmail_query()`, build Graph URL with `$search`/`$filter`/folder path
- `read_message(id)` → `GET /me/messages/{id}` → normalize to Gmail-like payload format
- `read_thread(id)` → `GET /me/messages?$filter=conversationId eq '{id}'`
- `create_draft()` → `POST /me/messages` with Graph JSON format + attachments
- `send_email()` → `POST /me/sendMail` with attachments
- `send_draft()` → `POST /me/messages/{id}/send`
- `list_labels()` → `GET /me/mailFolders` + `GET /me/outlook/masterCategories` → normalize
- Attachments <3MB: inline `contentBytes`; >=3MB: upload session

The implementation normalizes all responses to match Gmail's format so tool handlers work unchanged.

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/unit/test_outlook_client.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/outlook_client.py tests/unit/test_outlook_client.py
git commit -m "feat: OutlookClient via Microsoft Graph API"
```

---

### Task 7: Config + accounts.json Loading

**Files:**
- Modify: `src/config.py`
- Create: `accounts.json`
- Modify: `src/account_registry.py` — add `load_from_config` method
- Modify: `requirements.txt`

- [ ] **Step 1: Update Config to load accounts.json and Microsoft settings**

Modify `src/config.py`:
```python
class Config:
    def __init__(self) -> None:
        self.client_secret_path: str = os.getenv(
            "GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json"
        )
        self.token_path: str = os.getenv("GOOGLE_TOKEN_PATH", "credentials/token.json")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_file: str = os.getenv("LOG_FILE", "mcp_server.log")
        self.accounts_path: str = os.getenv("ACCOUNTS_PATH", "accounts.json")
        self.mcp_auth_token: str | None = os.getenv("MCP_AUTH_TOKEN")
        self.http_port: int = int(os.getenv("HTTP_PORT", "8420"))

    def load_accounts(self) -> list[dict[str, Any]]:
        path = Path(self.accounts_path)
        if not path.exists():
            return [{"email": "default", "provider": "gmail"}]
        data = json.loads(path.read_text())
        return data.get("accounts", [])

    def get_default_account(self) -> str | None:
        path = Path(self.accounts_path)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return data.get("default")
```

- [ ] **Step 2: Add `load_from_config` to AccountRegistry**

```python
def load_from_config(self, cfg: Config) -> None:
    accounts = cfg.load_accounts()
    default = cfg.get_default_account()
    for acc in accounts:
        email = acc["email"]
        provider = acc["provider"]
        if provider == "gmail":
            from .auth import TokenManager
            from .gmail_client import GmailClient
            token_path = f"credentials/{email}/token.json"
            tmgr = TokenManager(cfg.client_secret_path, token_path)
            client = GmailClient(tmgr, email)
        elif provider == "outlook":
            from .auth import MicrosoftTokenManager
            from .outlook_client import OutlookClient
            ms_cfg = acc.get("azure", {})
            token_path = f"credentials/{email}/token.json"
            tmgr = MicrosoftTokenManager(
                client_id=ms_cfg.get("client_id", ""),
                tenant_id=ms_cfg.get("tenant_id", ""),
                token_path=token_path,
            )
            client = OutlookClient(tmgr, email)
        else:
            continue
        self.register(email, client, default=(email == default))
```

- [ ] **Step 3: Create accounts.json**

```json
{
  "default": "jpastore79@gmail.com",
  "accounts": [
    {
      "email": "jpastore79@gmail.com",
      "provider": "gmail"
    },
    {
      "email": "jon@degenito.ai",
      "provider": "outlook",
      "azure": {
        "client_id": "",
        "tenant_id": ""
      }
    }
  ]
}
```

- [ ] **Step 4: Update requirements.txt**

```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
pydantic>=2.5.0,<3.0.0
python-dotenv>=1.0.0
loguru>=0.7.0
requests>=2.31.0
msal>=1.28.0
mcp>=1.0.0
uvicorn>=0.30.0
starlette>=0.38.0
httpx>=0.27.0

# Dev dependencies
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-asyncio>=0.24.0
mypy>=1.8.0
ruff>=0.3.0
```

- [ ] **Step 5: Update .env.example**

```
GOOGLE_CLIENT_SECRET_PATH=credentials/client_secret.json
ACCOUNTS_PATH=accounts.json
LOG_LEVEL=INFO
LOG_FILE=mcp_server.log
MCP_AUTH_TOKEN=your-secret-bearer-token-here
HTTP_PORT=8420
```

- [ ] **Step 6: Run all tests**

```bash
pip install msal mcp uvicorn starlette httpx
python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/config.py src/account_registry.py accounts.json requirements.txt .env.example
git commit -m "feat: accounts.json config, Microsoft settings, updated deps"
```

---

### Task 8: Update main.py — CLI Commands

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Update main.py with serve and auth --provider commands**

```python
from __future__ import annotations

import sys

from loguru import logger

from .config import Config, setup_logging


def main() -> None:
    cfg = Config()
    setup_logging(cfg)

    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        provider = "gmail"
        for i, arg in enumerate(sys.argv):
            if arg == "--provider" and i + 1 < len(sys.argv):
                provider = sys.argv[i + 1]
        from .auth import run_auth_flow
        run_auth_flow(cfg, provider=provider)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        port = cfg.http_port
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        from .http_server import run_http_server
        run_http_server(cfg, port=port)
        return

    try:
        logger.info("Starting Gmail Enhanced MCP Server v2.0.0 (stdio)")
        from .protocol import ProtocolHandler
        from .server import StdioServer
        server = StdioServer()
        handler = ProtocolHandler()
        server.run(handler.handle_request)
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: CLI commands — serve and auth --provider"
```

---

### Task 9: Streamable HTTP Transport

**Files:**
- Create: `src/http_server.py`
- Create: `tests/integration/test_http_server.py`

- [ ] **Step 1: Write HTTP server tests**

Create `tests/integration/test_http_server.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    with patch("src.http_server.AccountRegistry") as mock_reg_cls, \
         patch("src.http_server.Config"):
        mock_reg = MagicMock()
        mock_reg.list_accounts.return_value = [{"email": "test@gmail.com", "provider": "gmail"}]
        mock_reg_cls.return_value = mock_reg

        from src.http_server import create_app
        from starlette.testclient import TestClient

        app = create_app(MagicMock())
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_mcp_endpoint_requires_auth() -> None:
    with patch("src.http_server.AccountRegistry") as mock_reg_cls, \
         patch("src.http_server.Config"):
        mock_reg = MagicMock()
        mock_reg_cls.return_value = mock_reg

        from src.http_server import create_app
        from starlette.testclient import TestClient

        cfg = MagicMock()
        cfg.mcp_auth_token = "secret123"
        app = create_app(cfg)
        client = TestClient(app)

        resp = client.post("/mcp", json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
        assert resp.status_code == 401

        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Authorization": "Bearer secret123"},
        )
        assert resp.status_code != 401
```

- [ ] **Step 2: Implement HTTP server**

Create `src/http_server.py`:

```python
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from loguru import logger
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import CallToolResult, TextContent, Tool

from .account_registry import AccountRegistry
from .config import Config
from .tools import TOOL_DEFINITIONS, ToolRegistry


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, token: str, exempt_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self._token = token
        self._exempt = exempt_paths or {"/health"}

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path in self._exempt:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self._token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_mcp_server(registry: AccountRegistry) -> Server:
    server = Server("gmail-enhanced-mcp")
    tool_registry = ToolRegistry(account_registry=registry)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = tool_registry.list_tools()
        return [
            Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t["inputSchema"],
            )
            for t in tools
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        from .models import ToolCallParams
        params = ToolCallParams(name=name, arguments=arguments)
        result = tool_registry.execute_tool(params)
        content = result.get("content", [])
        return [TextContent(type="text", text=c.get("text", "")) for c in content]

    return server


def create_app(cfg: Config) -> Starlette:
    registry = AccountRegistry()
    registry.load_from_config(cfg)
    mcp_server = create_mcp_server(registry)
    session_manager = StreamableHTTPSessionManager(app=mcp_server)

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "version": "2.0.0"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("HTTP server started")
            yield
            logger.info("HTTP server stopped")

    middleware = []
    if cfg.mcp_auth_token:
        middleware.append(
            Middleware(BearerAuthMiddleware, token=cfg.mcp_auth_token, exempt_paths={"/health"})
        )

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=session_manager.handle_request),
        ],
        lifespan=lifespan,
        middleware=middleware,
    )


def run_http_server(cfg: Config, port: int = 8420) -> None:
    if not cfg.mcp_auth_token:
        logger.warning("MCP_AUTH_TOKEN not set — HTTP server running without auth!")
    logger.info(f"Starting HTTP server on port {port}")
    app = create_app(cfg)
    uvicorn.run(app, host="0.0.0.0", port=port)
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/integration/test_http_server.py -v
```

Expected: Tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/http_server.py tests/integration/test_http_server.py
git commit -m "feat: Streamable HTTP transport with bearer auth"
```

---

### Task 10: Deployment Docs + Final Wiring

**Files:**
- Create: `DEPLOY.md`
- Modify: `.mcp.json`
- Update: `.env.example`

- [ ] **Step 1: Create DEPLOY.md**

Create `DEPLOY.md` with complete Mac Mini deployment instructions:
1. Prerequisites (Python 3.11+, pip, cloudflared, git)
2. Clone and install
3. Auth setup for each account
4. accounts.json configuration
5. .env with MCP_AUTH_TOKEN
6. Claude Desktop config (claude_desktop_config.json)
7. launchd plist for auto-start
8. Cloudflare tunnel setup (persistent daemon)
9. Mobile setup (Claude app remote MCP URL)
10. Troubleshooting

- [ ] **Step 2: Update .mcp.json for dual mode**

```json
{
  "mcpServers": {
    "gmail-enhanced": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "gmail_mcp"],
      "cwd": "/home/jon/projects/gmail-enhanced-mcp"
    }
  }
}
```

(No change for local Claude Code — stdio stays as-is. The HTTP mode is for Claude Desktop/mobile.)

- [ ] **Step 3: Run full test suite with coverage**

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing -v
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
```

- [ ] **Step 4: Commit**

```bash
git add DEPLOY.md .mcp.json .env.example
git commit -m "docs: Mac Mini deployment guide + final wiring"
```

---

## Post-Implementation Checklist

- [ ] EmailClient ABC with all 13 methods
- [ ] GmailClient extends EmailClient, all existing tests still pass
- [ ] OutlookClient implements EmailClient via Microsoft Graph
- [ ] Query translator handles all 15+ Gmail search operators
- [ ] AccountRegistry routes by account param
- [ ] All tools have `account` parameter in schemas
- [ ] `list_accounts` tool works
- [ ] HTTP server starts with `python -m gmail_mcp serve`
- [ ] Bearer token auth blocks unauthorized requests
- [ ] Health endpoint works without auth
- [ ] `python -m gmail_mcp auth --provider outlook` works
- [ ] `python -m gmail_mcp auth --provider gmail` still works
- [ ] accounts.json loaded on startup
- [ ] Multiple Gmail accounts work
- [ ] DEPLOY.md covers Mac Mini + Cloudflare tunnel + Claude Desktop
- [ ] Coverage ≥ 90% for new code
- [ ] ruff + mypy clean
