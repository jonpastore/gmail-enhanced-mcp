# Gmail Enhanced MCP — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that provides full Gmail API access with attachment support via Claude Code's stdio transport.

**Architecture:** Stdio JSON-RPC 2.0 server modeled on chatgpt5-mcp-server. Tools call `gmail_client.py` (the only file touching the Gmail API). Pydantic validates all inputs. Loguru handles logging with rotation.

**Tech Stack:** Python 3.11+, google-api-python-client, google-auth-oauthlib, Pydantic 2.x, Loguru, pytest

---

## File Map

| File | Responsibility |
|------|---------------|
| `src/__init__.py` | Package marker |
| `src/main.py` | Entry point — launches stdio server, handles auth CLI |
| `src/server.py` | Stdin/stdout JSON-RPC communication loop |
| `src/protocol.py` | MCP method routing (initialize, tools/list, tools/call) |
| `src/models.py` | Pydantic models for JSON-RPC + tool inputs |
| `src/config.py` | Config singleton + logging setup |
| `src/auth.py` | OAuth2 flow + token load/refresh/save |
| `src/gmail_client.py` | Gmail API wrapper — all Google API calls |
| `src/tools/__init__.py` | Tool registry — maps tool names to handlers |
| `src/tools/search.py` | get_profile, search_messages, read_message, read_thread |
| `src/tools/drafts.py` | create_draft, update_draft, list_drafts, send_draft |
| `src/tools/send.py` | send_email with attachments |
| `src/tools/labels.py` | list_labels, modify_thread_labels |
| `src/tools/attachments.py` | download_attachment, resolve attachment sources to bytes |
| `src/tools/templates.py` | save_template, use_template |
| `gmail_mcp/__init__.py` | Package entry for `python -m gmail_mcp` |
| `gmail_mcp/__main__.py` | Calls `src.main.main()` |
| `tests/conftest.py` | Shared fixtures: mock_gmail_client, sample data |
| `tests/fixtures/` | JSON files with realistic Gmail API responses |

---

### Task 1: Foundation — Config, Models, Server, Protocol

**Files:**
- Create: `src/__init__.py`, `src/config.py`, `src/models.py`, `src/server.py`, `src/protocol.py`
- Create: `src/main.py`, `gmail_mcp/__init__.py`, `gmail_mcp/__main__.py`
- Create: `tests/conftest.py`, `tests/unit/test_models.py`, `tests/unit/test_server.py`, `tests/unit/test_protocol.py`

- [ ] **Step 1: Install dependencies**

```bash
cd /home/jon/projects/gmail-enhanced-mcp
python -m pip install -r requirements.txt
```

- [ ] **Step 2: Write test for Pydantic models**

Create `tests/unit/test_models.py`:

```python
from __future__ import annotations

import pytest
from src.models import (
    JsonRpcRequest,
    ToolCallParams,
    InitializeParams,
    AttachmentSource,
    ERROR_CODES,
)


class TestJsonRpcRequest:
    def test_valid_request_parses(self) -> None:
        req = JsonRpcRequest(jsonrpc="2.0", method="tools/list", id=1)
        assert req.method == "tools/list"
        assert req.id == 1

    def test_invalid_jsonrpc_version_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON-RPC version"):
            JsonRpcRequest(jsonrpc="1.0", method="test", id=1)

    def test_params_default_to_none(self) -> None:
        req = JsonRpcRequest(jsonrpc="2.0", method="test", id=1)
        assert req.params is None


class TestToolCallParams:
    def test_valid_tool_call(self) -> None:
        params = ToolCallParams(name="gmail_search_messages", arguments={"q": "test"})
        assert params.name == "gmail_search_messages"
        assert params.arguments == {"q": "test"}

    def test_arguments_default_to_empty(self) -> None:
        params = ToolCallParams(name="gmail_get_profile")
        assert params.arguments == {}


class TestAttachmentSource:
    def test_file_attachment(self) -> None:
        att = AttachmentSource(type="file", path="/tmp/test.pdf")
        assert att.type == "file"
        assert att.path == "/tmp/test.pdf"

    def test_gmail_attachment(self) -> None:
        att = AttachmentSource(
            type="gmail", message_id="abc", attachment_id="def"
        )
        assert att.type == "gmail"

    def test_url_attachment(self) -> None:
        att = AttachmentSource(
            type="url", url="https://example.com/doc.pdf", filename="doc.pdf"
        )
        assert att.type == "url"

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError):
            AttachmentSource(type="ftp", path="/tmp/test.pdf")


class TestErrorCodes:
    def test_standard_codes_present(self) -> None:
        assert ERROR_CODES["PARSE_ERROR"] == -32700
        assert ERROR_CODES["METHOD_NOT_FOUND"] == -32601
        assert ERROR_CODES["INTERNAL_ERROR"] == -32603
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest tests/unit/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.models'`

- [ ] **Step 4: Implement models**

Create `src/__init__.py`:

```python
```

Create `src/models.py`:

```python
from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, field_validator


class JsonRpcRequest(BaseModel):
    jsonrpc: str
    method: str
    params: Optional[dict[str, Any]] = None
    id: Optional[Union[int, str]] = None

    @field_validator("jsonrpc")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "2.0":
            raise ValueError(f"Invalid JSON-RPC version: {v}")
        return v


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict[str, Any]] = None
    id: Optional[Union[int, str]] = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class InitializeParams(BaseModel):
    protocolVersion: str
    capabilities: dict[str, Any] = {}
    clientInfo: Optional[dict[str, str]] = None


class ToolCallParams(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class AttachmentSource(BaseModel):
    type: str
    path: Optional[str] = None
    message_id: Optional[str] = None
    attachment_id: Optional[str] = None
    url: Optional[str] = None
    filename: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("file", "gmail", "url"):
            raise ValueError(f"Invalid attachment type: {v}. Must be file, gmail, or url")
        return v


ERROR_CODES: dict[str, int] = {
    "PARSE_ERROR": -32700,
    "INVALID_REQUEST": -32600,
    "METHOD_NOT_FOUND": -32601,
    "INVALID_PARAMS": -32602,
    "INTERNAL_ERROR": -32603,
    "SERVER_ERROR": -32000,
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest tests/unit/test_models.py -v
```

Expected: All 9 tests PASS

- [ ] **Step 6: Write test for config**

Create `tests/unit/test_config.py`:

```python
from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config


class TestConfig:
    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            assert cfg.log_level == "INFO"
            assert cfg.log_file == "mcp_server.log"
            assert cfg.client_secret_path == "credentials/client_secret.json"
            assert cfg.token_path == "credentials/token.json"

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG", "LOG_FILE": "/tmp/test.log"}):
            cfg = Config()
            assert cfg.log_level == "DEBUG"
            assert cfg.log_file == "/tmp/test.log"
```

- [ ] **Step 7: Implement config**

Create `src/config.py`:

```python
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from loguru import logger

load_dotenv()


class Config:
    def __init__(self) -> None:
        self.client_secret_path: str = os.getenv(
            "GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json"
        )
        self.token_path: str = os.getenv(
            "GOOGLE_TOKEN_PATH", "credentials/token.json"
        )
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_file: str = os.getenv("LOG_FILE", "mcp_server.log")


def setup_logging(cfg: Config) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=cfg.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    if cfg.log_file:
        logger.add(
            cfg.log_file,
            rotation="10 MB",
            retention=3,
            level=cfg.log_level,
        )
```

- [ ] **Step 8: Run config tests**

```bash
python -m pytest tests/unit/test_config.py -v
```

Expected: 2 tests PASS

- [ ] **Step 9: Write test for server**

Create `tests/unit/test_server.py`:

```python
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

from src.server import StdioServer


class TestStdioServer:
    def test_read_message_parses_json(self) -> None:
        msg = {"jsonrpc": "2.0", "method": "test", "id": 1}
        server = StdioServer()
        server._stdin = io.StringIO(json.dumps(msg) + "\n")
        result = server.read_message()
        assert result == msg

    def test_read_message_returns_none_on_eof(self) -> None:
        server = StdioServer()
        server._stdin = io.StringIO("")
        result = server.read_message()
        assert result is None

    def test_send_response_writes_json(self) -> None:
        server = StdioServer()
        output = io.StringIO()
        server._stdout = output
        response = {"jsonrpc": "2.0", "result": "ok", "id": 1}
        server.send_response(response)
        written = output.getvalue()
        assert json.loads(written.strip()) == response

    def test_run_processes_messages(self) -> None:
        msg = {"jsonrpc": "2.0", "method": "test", "id": 1}
        response = {"jsonrpc": "2.0", "result": "ok", "id": 1}
        handler = MagicMock(return_value=response)
        server = StdioServer()
        server._stdin = io.StringIO(json.dumps(msg) + "\n")
        output = io.StringIO()
        server._stdout = output
        server.run(handler)
        handler.assert_called_once_with(msg)
```

- [ ] **Step 10: Implement server**

Create `src/server.py`:

```python
from __future__ import annotations

import json
import sys
from typing import Any, Callable, Optional, Union

from loguru import logger

from .models import ERROR_CODES


class StdioServer:
    def __init__(self) -> None:
        self.buffer = ""
        self.decoder = json.JSONDecoder()
        self._stdin = sys.stdin
        self._stdout = sys.stdout

    def read_message(self) -> Optional[Union[dict[str, Any], list[dict[str, Any]]]]:
        while True:
            try:
                line = self._stdin.readline()
                if not line:
                    return None

                self.buffer += line

                if not self.buffer.strip():
                    continue

                try:
                    message, index = self.decoder.raw_decode(self.buffer)
                    self.buffer = self.buffer[index:].lstrip()
                    return message
                except json.JSONDecodeError:
                    if "\n" in self.buffer and len(self.buffer) > 10000:
                        logger.error("Buffer overflow, clearing")
                        self.buffer = ""
                        return {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": ERROR_CODES["PARSE_ERROR"],
                                "message": "Buffer overflow",
                            },
                            "id": None,
                        }
                    if "\n" in self.buffer:
                        logger.error("JSON parse error, clearing buffer")
                        self.buffer = ""
                    continue

            except KeyboardInterrupt:
                return None
            except Exception as e:
                logger.error(f"Error reading message: {e}")
                self.buffer = ""
                return None

    def send_response(self, response: Optional[Union[dict[str, Any], list[dict[str, Any]]]]) -> None:
        if response is None:
            return
        try:
            output = json.dumps(response)
            self._stdout.write(output + "\n")
            self._stdout.flush()
        except Exception as e:
            logger.error(f"Error sending response: {e}")

    def run(self, handler: Callable[[dict[str, Any]], Optional[dict[str, Any]]]) -> None:
        logger.info("MCP Server starting...")
        while True:
            message = self.read_message()
            if message is None:
                logger.info("Server shutting down")
                break
            try:
                if isinstance(message, list):
                    responses = [
                        r for msg in message if (r := handler(msg)) is not None
                    ]
                    if responses:
                        self.send_response(responses)
                else:
                    response = handler(message)
                    if response is not None:
                        self.send_response(response)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": ERROR_CODES["INTERNAL_ERROR"],
                        "message": str(e),
                    },
                    "id": message.get("id") if isinstance(message, dict) else None,
                }
                self.send_response(error_response)
```

- [ ] **Step 11: Run server tests**

```bash
python -m pytest tests/unit/test_server.py -v
```

Expected: 4 tests PASS

- [ ] **Step 12: Write test for protocol**

Create `tests/unit/test_protocol.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.protocol import ProtocolHandler


class TestProtocolHandler:
    def test_initialize_returns_server_info(self) -> None:
        handler = ProtocolHandler.__new__(ProtocolHandler)
        handler.initialized = False
        handler.tool_registry = MagicMock()
        result = handler.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                },
                "id": 1,
            }
        )
        assert result["result"]["serverInfo"]["name"] == "gmail-enhanced-mcp"
        assert result["result"]["capabilities"]["tools"] == {}
        assert result["id"] == 1

    def test_initialized_notification_returns_none(self) -> None:
        handler = ProtocolHandler.__new__(ProtocolHandler)
        handler.initialized = False
        handler.tool_registry = MagicMock()
        result = handler.handle_request(
            {"jsonrpc": "2.0", "method": "initialized"}
        )
        assert result is None
        assert handler.initialized is True

    def test_tools_list_returns_tools(self) -> None:
        handler = ProtocolHandler.__new__(ProtocolHandler)
        handler.initialized = True
        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = [{"name": "test_tool"}]
        handler.tool_registry = mock_registry
        result = handler.handle_request(
            {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2}
        )
        assert result["result"]["tools"] == [{"name": "test_tool"}]

    def test_unknown_method_returns_error(self) -> None:
        handler = ProtocolHandler.__new__(ProtocolHandler)
        handler.initialized = True
        handler.tool_registry = MagicMock()
        result = handler.handle_request(
            {"jsonrpc": "2.0", "method": "nonexistent", "id": 3}
        )
        assert result["error"]["code"] == -32601

    def test_tools_call_delegates_to_registry(self) -> None:
        handler = ProtocolHandler.__new__(ProtocolHandler)
        handler.initialized = True
        mock_registry = MagicMock()
        mock_registry.execute_tool.return_value = {
            "content": [{"type": "text", "text": "result"}]
        }
        handler.tool_registry = mock_registry
        result = handler.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "gmail_get_profile", "arguments": {}},
                "id": 4,
            }
        )
        assert result["result"]["content"][0]["text"] == "result"
```

- [ ] **Step 13: Implement protocol**

Create `src/protocol.py`:

```python
from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from pydantic import ValidationError

from .models import (
    ERROR_CODES,
    InitializeParams,
    JsonRpcRequest,
    ToolCallParams,
)
from .tools import ToolRegistry


class ProtocolHandler:
    def __init__(self) -> None:
        self.tool_registry = ToolRegistry()
        self.initialized = False

    def handle_request(self, raw_request: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            request = JsonRpcRequest(**raw_request)

            if request.id is None and request.method == "initialized":
                logger.info("Received 'initialized' notification")
                self.initialized = True
                return None

            method_handler = self._get_method_handler(request.method)
            if not method_handler:
                return self._error_response(
                    ERROR_CODES["METHOD_NOT_FOUND"],
                    f"Method not found: {request.method}",
                    request.id,
                )

            result = method_handler(request.params or {})
            return self._success_response(result, request.id)

        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return self._error_response(
                ERROR_CODES["INVALID_REQUEST"],
                f"Invalid request: {e}",
                raw_request.get("id"),
            )
        except ValueError as e:
            logger.error(f"Value error: {e}")
            return self._error_response(
                ERROR_CODES["INVALID_PARAMS"],
                str(e),
                raw_request.get("id"),
            )
        except Exception as e:
            logger.error(f"Internal error: {e}")
            return self._error_response(
                ERROR_CODES["INTERNAL_ERROR"],
                f"Internal error: {e}",
                raw_request.get("id"),
            )

    def _get_method_handler(self, method: str) -> Optional[Any]:
        handlers: dict[str, Any] = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
        }
        return handlers.get(method)

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        init_params = InitializeParams(**params)
        logger.info(f"Initializing with protocol version: {init_params.protocolVersion}")
        self.initialized = True
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "gmail-enhanced-mcp", "version": "1.0.0"},
        }

    def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        tools = self.tool_registry.list_tools()
        return {"tools": tools}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.initialized:
            raise ValueError("Server not initialized")
        tool_params = ToolCallParams(**params)
        return self.tool_registry.execute_tool(tool_params)

    def _success_response(
        self, result: Any, request_id: Optional[int | str]
    ) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "result": result, "id": request_id}

    def _error_response(
        self, code: int, message: str, request_id: Optional[int | str]
    ) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": request_id,
        }
```

- [ ] **Step 14: Create tool registry stub**

Create `src/tools/__init__.py`:

```python
from __future__ import annotations

from typing import Any

from loguru import logger

from ..models import ToolCallParams


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Any] = {}

    def register(
        self, name: str, description: str, input_schema: dict[str, Any], handler: Any
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        self._handlers[name] = handler

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    def execute_tool(self, params: ToolCallParams) -> dict[str, Any]:
        handler = self._handlers.get(params.name)
        if handler is None:
            raise ValueError(f"Unknown tool: {params.name}")
        logger.info(f"Executing tool: {params.name}")
        result = handler(params.arguments)
        return result
```

- [ ] **Step 15: Create entry point**

Create `gmail_mcp/__init__.py`:

```python
```

Create `gmail_mcp/__main__.py`:

```python
from src.main import main

main()
```

Create `src/main.py`:

```python
from __future__ import annotations

import sys

from loguru import logger

from .config import Config, setup_logging
from .protocol import ProtocolHandler
from .server import StdioServer


def main() -> None:
    cfg = Config()
    setup_logging(cfg)

    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        from .auth import run_auth_flow

        run_auth_flow(cfg)
        return

    try:
        logger.info("Starting Gmail Enhanced MCP Server v1.0.0")
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

- [ ] **Step 16: Create conftest with shared fixtures**

Create `tests/__init__.py`:

```python
```

Create `tests/unit/__init__.py`:

```python
```

Create `tests/unit/tools/__init__.py`:

```python
```

Create `tests/integration/__init__.py`:

```python
```

Create `tests/conftest.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_gmail_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_gmail_client(mock_gmail_service: MagicMock) -> MagicMock:
    client = MagicMock()
    client.service = mock_gmail_service
    return client


@pytest.fixture
def sample_message() -> dict[str, Any]:
    return {
        "id": "msg_001",
        "threadId": "thread_001",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Hello, this is a test email",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "jpastore79@gmail.com"},
                {"name": "Subject", "value": "Test Email"},
                {"name": "Date", "value": "Mon, 10 Mar 2026 10:00:00 -0500"},
            ],
            "body": {"data": "SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IGVtYWls", "size": 27},
            "parts": [],
        },
        "sizeEstimate": 1024,
        "internalDate": "1741608000000",
    }


@pytest.fixture
def sample_thread(sample_message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "thread_001",
        "messages": [sample_message],
    }


@pytest.fixture
def sample_profile() -> dict[str, Any]:
    return {
        "emailAddress": "jpastore79@gmail.com",
        "messagesTotal": 50000,
        "threadsTotal": 25000,
        "historyId": "12345",
    }


@pytest.fixture
def tmp_template_dir(tmp_path: Path) -> Path:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    return tpl_dir


@pytest.fixture
def sample_attachment_bytes() -> bytes:
    return b"%PDF-1.4 fake pdf content for testing"
```

- [ ] **Step 17: Run all foundation tests**

```bash
python -m pytest tests/unit/test_models.py tests/unit/test_config.py tests/unit/test_server.py tests/unit/test_protocol.py -v
```

Expected: All tests PASS

- [ ] **Step 18: Commit foundation**

```bash
git add src/ gmail_mcp/ tests/ requirements.txt pyproject.toml package.json .env.example .gitignore CLAUDE.md docs/ .claude/
git commit -m "feat: foundation — config, models, server, protocol, tool registry"
```

---

### Task 2: Auth — OAuth2 Flow + Token Management

**Files:**
- Create: `src/auth.py`
- Create: `tests/unit/test_auth.py`

- [ ] **Step 1: Write auth tests**

Create `tests/unit/test_auth.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.auth import TokenManager


class TestTokenManager:
    def test_load_token_from_file(self, tmp_path: Path) -> None:
        token_data = {
            "token": "access_123",
            "refresh_token": "refresh_456",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        }
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps(token_data))

        mgr = TokenManager(
            client_secret_path=str(tmp_path / "client_secret.json"),
            token_path=str(token_file),
        )
        creds = mgr.load_token()
        assert creds is not None

    def test_load_token_returns_none_when_missing(self, tmp_path: Path) -> None:
        mgr = TokenManager(
            client_secret_path=str(tmp_path / "client_secret.json"),
            token_path=str(tmp_path / "nonexistent.json"),
        )
        creds = mgr.load_token()
        assert creds is None

    def test_save_token_writes_file(self, tmp_path: Path) -> None:
        token_file = tmp_path / "token.json"
        mgr = TokenManager(
            client_secret_path=str(tmp_path / "client_secret.json"),
            token_path=str(token_file),
        )
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "saved"}'
        mgr.save_token(mock_creds)
        assert token_file.exists()
        assert json.loads(token_file.read_text()) == {"token": "saved"}

    def test_get_credentials_refreshes_expired_token(self, tmp_path: Path) -> None:
        token_data = {
            "token": "expired",
            "refresh_token": "refresh_456",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "cid",
            "client_secret": "csec",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        }
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps(token_data))

        mgr = TokenManager(
            client_secret_path=str(tmp_path / "cs.json"),
            token_path=str(token_file),
        )

        with patch("src.auth.Credentials") as mock_creds_cls:
            mock_creds = MagicMock()
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = "refresh_456"
            mock_creds.to_json.return_value = '{"token": "refreshed"}'
            mock_creds_cls.from_authorized_user_info.return_value = mock_creds

            creds = mgr.get_credentials()
            mock_creds.refresh.assert_called_once()

    def test_get_credentials_raises_when_no_token(self, tmp_path: Path) -> None:
        mgr = TokenManager(
            client_secret_path=str(tmp_path / "cs.json"),
            token_path=str(tmp_path / "missing.json"),
        )
        with pytest.raises(RuntimeError, match="Not authenticated"):
            mgr.get_credentials()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_auth.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.auth'`

- [ ] **Step 3: Implement auth**

Create `src/auth.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger

from .config import Config

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


class TokenManager:
    def __init__(self, client_secret_path: str, token_path: str) -> None:
        self._client_secret_path = Path(client_secret_path)
        self._token_path = Path(token_path)
        self._cached_creds: Optional[Credentials] = None

    def load_token(self) -> Optional[Credentials]:
        if not self._token_path.exists():
            return None
        try:
            data = json.loads(self._token_path.read_text())
            return Credentials.from_authorized_user_info(data, SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
            return None

    def save_token(self, creds: Credentials) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())
        logger.info("Token saved")

    def get_credentials(self) -> Credentials:
        if self._cached_creds and self._cached_creds.valid:
            return self._cached_creds

        creds = self.load_token()
        if creds is None:
            raise RuntimeError(
                "Not authenticated. Run: python -m gmail_mcp auth"
            )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("Refreshing expired token")
                creds.refresh(Request())
                self.save_token(creds)
            else:
                raise RuntimeError(
                    "Token invalid and cannot refresh. Run: python -m gmail_mcp auth"
                )

        self._cached_creds = creds
        return creds


def run_auth_flow(cfg: Config) -> None:
    if not Path(cfg.client_secret_path).exists():
        logger.error(f"Client secret not found: {cfg.client_secret_path}")
        print(f"ERROR: Place client_secret.json at {cfg.client_secret_path}")
        print("Download from: Google Cloud Console > APIs & Services > Credentials")
        return

    flow = InstalledAppFlow.from_client_secrets_file(cfg.client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0)

    mgr = TokenManager(cfg.client_secret_path, cfg.token_path)
    mgr.save_token(creds)
    print("Authentication successful! Token saved.")
```

- [ ] **Step 4: Run auth tests**

```bash
python -m pytest tests/unit/test_auth.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/auth.py tests/unit/test_auth.py
git commit -m "feat: OAuth2 token management with load/save/refresh"
```

---

### Task 3: Gmail Client — API Wrapper

**Files:**
- Create: `src/gmail_client.py`
- Create: `tests/unit/test_gmail_client.py`

- [ ] **Step 1: Write gmail_client tests**

Create `tests/unit/test_gmail_client.py`:

```python
from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.gmail_client import GmailClient


def _make_client(mock_service: MagicMock | None = None) -> GmailClient:
    client = GmailClient.__new__(GmailClient)
    client._service = mock_service or MagicMock()
    return client


class TestGetProfile:
    def test_returns_profile_data(self, sample_profile: dict[str, Any]) -> None:
        mock_svc = MagicMock()
        mock_svc.users().getProfile().execute.return_value = sample_profile
        client = _make_client(mock_svc)
        result = client.get_profile()
        assert result["emailAddress"] == "jpastore79@gmail.com"


class TestSearchMessages:
    def test_returns_messages_list(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_001", "threadId": "t_001"}],
            "resultSizeEstimate": 1,
        }
        client = _make_client(mock_svc)
        result = client.search_messages(q="from:test@example.com", max_results=10)
        assert len(result["messages"]) == 1

    def test_empty_results(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        client = _make_client(mock_svc)
        result = client.search_messages(q="nonexistent")
        assert result["messages"] == []


class TestReadMessage:
    def test_returns_full_message(self, sample_message: dict[str, Any]) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = sample_message
        client = _make_client(mock_svc)
        result = client.read_message("msg_001")
        assert result["id"] == "msg_001"


class TestReadThread:
    def test_returns_thread_with_messages(
        self, sample_thread: dict[str, Any]
    ) -> None:
        mock_svc = MagicMock()
        mock_svc.users().threads().get().execute.return_value = sample_thread
        client = _make_client(mock_svc)
        result = client.read_thread("thread_001")
        assert result["id"] == "thread_001"
        assert len(result["messages"]) == 1


class TestBuildMimeMessage:
    def test_plain_text_no_attachments(self) -> None:
        client = _make_client()
        mime_msg = client.build_mime_message(
            to="test@example.com",
            subject="Test",
            body="Hello",
            content_type="text/plain",
        )
        assert mime_msg["To"] == "test@example.com"
        assert mime_msg["Subject"] == "Test"

    def test_with_file_attachment(self, tmp_path: Any) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test content")
        client = _make_client()
        mime_msg = client.build_mime_message(
            to="test@example.com",
            subject="Test",
            body="See attached",
            content_type="text/plain",
            attachments=[{"type": "file", "path": str(pdf)}],
        )
        assert mime_msg.get_content_type() == "multipart/mixed"

    def test_missing_file_raises(self) -> None:
        client = _make_client()
        with pytest.raises(FileNotFoundError, match="does not exist"):
            client.build_mime_message(
                to="test@example.com",
                subject="Test",
                body="Hello",
                content_type="text/plain",
                attachments=[{"type": "file", "path": "/nonexistent/file.pdf"}],
            )


class TestCreateDraft:
    def test_creates_draft_and_returns_id(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().drafts().create().execute.return_value = {
            "id": "draft_001",
            "message": {"id": "msg_draft_001"},
        }
        client = _make_client(mock_svc)
        result = client.create_draft(
            to="test@example.com",
            subject="Draft Test",
            body="Body",
            content_type="text/plain",
        )
        assert result["id"] == "draft_001"


class TestSendDraft:
    def test_sends_draft_by_id(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().drafts().send().execute.return_value = {
            "id": "msg_sent_001",
            "labelIds": ["SENT"],
        }
        client = _make_client(mock_svc)
        result = client.send_draft("draft_001")
        assert result["id"] == "msg_sent_001"


class TestSendEmail:
    def test_sends_email_directly(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().send().execute.return_value = {
            "id": "msg_sent_002",
            "labelIds": ["SENT"],
        }
        client = _make_client(mock_svc)
        result = client.send_email(
            to="test@example.com",
            subject="Direct Send",
            body="Body",
            content_type="text/plain",
        )
        assert result["id"] == "msg_sent_002"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_gmail_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.gmail_client'`

- [ ] **Step 3: Implement gmail_client**

Create `src/gmail_client.py`:

```python
from __future__ import annotations

import base64
import mimetypes
from email.mime.application import MIMEApplication
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional

import requests
from googleapiclient.discovery import build
from loguru import logger

from .auth import TokenManager
from .config import Config

BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".scr", ".js", ".vbs", ".msi"}
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25MB


class GmailClient:
    def __init__(self, config: Config) -> None:
        self._token_mgr = TokenManager(config.client_secret_path, config.token_path)
        self._service: Any = None

    def _get_service(self) -> Any:
        if self._service is None:
            creds = self._token_mgr.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_profile(self) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().getProfile(userId="me").execute()

    def search_messages(
        self,
        q: str | None = None,
        max_results: int = 20,
        page_token: str | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        svc = self._get_service()
        kwargs: dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
            "includeSpamTrash": include_spam_trash,
        }
        if q:
            kwargs["q"] = q
        if page_token:
            kwargs["pageToken"] = page_token

        result = svc.users().messages().list(**kwargs).execute()
        return {
            "messages": result.get("messages", []),
            "nextPageToken": result.get("nextPageToken"),
            "resultSizeEstimate": result.get("resultSizeEstimate", 0),
        }

    def read_message(self, message_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()

    def download_attachment(
        self, message_id: str, attachment_id: str, save_path: str
    ) -> str:
        svc = self._get_service()
        att = svc.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        data = base64.urlsafe_b64decode(att["data"])
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info(f"Attachment saved: {len(data)} bytes")
        return str(path)

    def list_labels(self) -> list[dict[str, Any]]:
        svc = self._get_service()
        result = svc.users().labels().list(userId="me").execute()
        return result.get("labels", [])

    def modify_thread_labels(
        self,
        thread_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        svc = self._get_service()
        body: dict[str, Any] = {}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids
        return svc.users().threads().modify(
            userId="me", id=thread_id, body=body
        ).execute()

    def list_drafts(
        self, max_results: int = 20, page_token: str | None = None
    ) -> dict[str, Any]:
        svc = self._get_service()
        kwargs: dict[str, Any] = {"userId": "me", "maxResults": max_results}
        if page_token:
            kwargs["pageToken"] = page_token
        result = svc.users().drafts().list(**kwargs).execute()
        return {
            "drafts": result.get("drafts", []),
            "nextPageToken": result.get("nextPageToken"),
        }

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
        if attachments:
            msg = MIMEMultipart("mixed")
            text_part = MIMEText(body, "html" if content_type == "text/html" else "plain")
            msg.attach(text_part)
            for att in attachments:
                att_part = self._resolve_attachment(att)
                msg.attach(att_part)
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
        elif att_type == "gmail":
            return self._resolve_gmail_attachment(att["message_id"], att["attachment_id"])
        elif att_type == "url":
            return self._resolve_url_attachment(att["url"], att["filename"])
        else:
            raise ValueError(f"Unknown attachment type: {att_type}")

    def _resolve_file_attachment(self, file_path: str) -> MIMEBase:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Attachment path does not exist: {file_path}")
        if path.suffix.lower() in BLOCKED_EXTENSIONS:
            raise ValueError(f"Blocked attachment type: {path.suffix}")
        data = path.read_bytes()
        if len(data) > MAX_ATTACHMENT_SIZE:
            size_mb = len(data) / (1024 * 1024)
            raise ValueError(
                f"Attachment exceeds 25MB limit: {path.name} ({size_mb:.1f}MB)"
            )
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)

        if maintype == "image":
            part = MIMEImage(data, _subtype=subtype)
        elif maintype == "audio":
            part = MIMEAudio(data, _subtype=subtype)
        elif maintype == "application":
            part = MIMEApplication(data, _subtype=subtype)
        else:
            part = MIMEBase(maintype, subtype)
            part.set_payload(data)

        part.add_header(
            "Content-Disposition", "attachment", filename=path.name
        )
        return part

    def _resolve_gmail_attachment(
        self, message_id: str, attachment_id: str
    ) -> MIMEBase:
        svc = self._get_service()
        att = svc.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        data = base64.urlsafe_b64decode(att["data"])

        msg = svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        filename = self._find_attachment_filename(msg, attachment_id)
        mime_type, _ = mimetypes.guess_type(filename) if filename else (None, None)
        mime_type = mime_type or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)

        part = MIMEApplication(data, _subtype=subtype)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=filename or "attachment",
        )
        return part

    def _find_attachment_filename(
        self, message: dict[str, Any], attachment_id: str
    ) -> str | None:
        for part in message.get("payload", {}).get("parts", []):
            body = part.get("body", {})
            if body.get("attachmentId") == attachment_id:
                return part.get("filename")
        return None

    def _resolve_url_attachment(self, url: str, filename: str) -> MIMEBase:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.content
        if len(data) > MAX_ATTACHMENT_SIZE:
            size_mb = len(data) / (1024 * 1024)
            raise ValueError(
                f"URL attachment exceeds 25MB limit: {filename} ({size_mb:.1f}MB)"
            )
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        maintype = content_type.split("/")[0]
        subtype = content_type.split("/")[1].split(";")[0] if "/" in content_type else "octet-stream"

        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        return part

    def _encode_message(self, mime_msg: MIMEBase) -> str:
        return base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")

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
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to, subject=subject, body=body, content_type=content_type,
            cc=cc, bcc=bcc, thread_id=thread_id, attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        draft_body: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id
        svc = self._get_service()
        return svc.users().drafts().create(userId="me", body=draft_body).execute()

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
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to, subject=subject, body=body, content_type=content_type,
            cc=cc, bcc=bcc, attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        svc = self._get_service()
        return svc.users().drafts().update(
            userId="me", id=draft_id, body={"message": {"raw": raw}}
        ).execute()

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().drafts().send(
            userId="me", body={"id": draft_id}
        ).execute()

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to, subject=subject, body=body, content_type=content_type,
            cc=cc, bcc=bcc, attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        svc = self._get_service()
        return svc.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
```

- [ ] **Step 4: Run gmail_client tests**

```bash
python -m pytest tests/unit/test_gmail_client.py -v
```

Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/gmail_client.py tests/unit/test_gmail_client.py
git commit -m "feat: Gmail API client with MIME attachments, search, drafts, send"
```

---

### Task 4: Search Tools — get_profile, search_messages, read_message, read_thread

**Files:**
- Create: `src/tools/search.py`
- Create: `tests/unit/tools/test_search.py`

- [ ] **Step 1: Write search tool tests**

Create `tests/unit/tools/test_search.py`:

```python
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.tools.search import (
    handle_get_profile,
    handle_read_message,
    handle_read_thread,
    handle_search_messages,
)


class TestGetProfile:
    def test_returns_profile_as_text_content(
        self, sample_profile: dict[str, Any]
    ) -> None:
        mock_client = MagicMock()
        mock_client.get_profile.return_value = sample_profile
        result = handle_get_profile({}, mock_client)
        assert result["content"][0]["type"] == "text"
        assert "jpastore79@gmail.com" in result["content"][0]["text"]


class TestSearchMessages:
    def test_returns_message_list(self) -> None:
        mock_client = MagicMock()
        mock_client.search_messages.return_value = {
            "messages": [{"id": "m1", "threadId": "t1"}],
            "nextPageToken": None,
            "resultSizeEstimate": 1,
        }
        result = handle_search_messages(
            {"q": "from:test@example.com"}, mock_client
        )
        assert "m1" in result["content"][0]["text"]

    def test_empty_results(self) -> None:
        mock_client = MagicMock()
        mock_client.search_messages.return_value = {
            "messages": [],
            "nextPageToken": None,
            "resultSizeEstimate": 0,
        }
        result = handle_search_messages({"q": "nonexistent"}, mock_client)
        assert "No messages found" in result["content"][0]["text"]


class TestReadMessage:
    def test_returns_formatted_message(
        self, sample_message: dict[str, Any]
    ) -> None:
        mock_client = MagicMock()
        mock_client.read_message.return_value = sample_message
        result = handle_read_message({"messageId": "msg_001"}, mock_client)
        text = result["content"][0]["text"]
        assert "sender@example.com" in text
        assert "Test Email" in text

    def test_missing_message_id_raises(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="messageId is required"):
            handle_read_message({}, mock_client)


class TestReadThread:
    def test_returns_thread_messages(
        self, sample_thread: dict[str, Any]
    ) -> None:
        mock_client = MagicMock()
        mock_client.read_thread.return_value = sample_thread
        result = handle_read_thread({"threadId": "thread_001"}, mock_client)
        text = result["content"][0]["text"]
        assert "thread_001" in text

    def test_missing_thread_id_raises(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="threadId is required"):
            handle_read_thread({}, mock_client)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/tools/test_search.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement search tools**

Create `src/tools/search.py`:

```python
from __future__ import annotations

import base64
import json
from typing import Any

from ..gmail_client import GmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(body: dict[str, Any]) -> str:
    data = body.get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _format_message(msg: dict[str, Any]) -> str:
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    from_addr = _get_header(headers, "From")
    to_addr = _get_header(headers, "To")
    subject = _get_header(headers, "Subject")
    date = _get_header(headers, "Date")

    body_text = ""
    if payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                body_text = _decode_body(part.get("body", {}))
                break
        if not body_text:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    body_text = _decode_body(part.get("body", {}))
                    break
    else:
        body_text = _decode_body(payload.get("body", {}))

    attachments = []
    for part in payload.get("parts", []):
        if part.get("filename"):
            att_id = part.get("body", {}).get("attachmentId", "")
            attachments.append(
                f"  - {part['filename']} (id: {att_id})"
            )

    lines = [
        f"From: {from_addr}",
        f"To: {to_addr}",
        f"Subject: {subject}",
        f"Date: {date}",
        f"Message ID: {msg['id']}",
        f"Thread ID: {msg.get('threadId', '')}",
        f"Labels: {', '.join(msg.get('labelIds', []))}",
    ]
    if attachments:
        lines.append("Attachments:")
        lines.extend(attachments)
    lines.append("")
    lines.append(body_text)
    return "\n".join(lines)


def handle_get_profile(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    profile = client.get_profile()
    text = json.dumps(profile, indent=2)
    return _text_content(text)


def handle_search_messages(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    result = client.search_messages(
        q=args.get("q"),
        max_results=args.get("maxResults", 20),
        page_token=args.get("pageToken"),
        include_spam_trash=args.get("includeSpamTrash", False),
    )
    messages = result["messages"]
    if not messages:
        return _text_content("No messages found.")

    lines = [f"Found {result['resultSizeEstimate']} results:"]
    for msg in messages:
        lines.append(f"  - id: {msg['id']}  threadId: {msg['threadId']}")
    if result.get("nextPageToken"):
        lines.append(f"\nNext page token: {result['nextPageToken']}")
    return _text_content("\n".join(lines))


def handle_read_message(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    message_id = args.get("messageId")
    if not message_id:
        raise ValueError("messageId is required")
    msg = client.read_message(message_id)
    return _text_content(_format_message(msg))


def handle_read_thread(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    thread_id = args.get("threadId")
    if not thread_id:
        raise ValueError("threadId is required")
    thread = client.read_thread(thread_id)
    lines = [f"Thread: {thread['id']}", f"Messages: {len(thread['messages'])}", "---"]
    for msg in thread["messages"]:
        lines.append(_format_message(msg))
        lines.append("---")
    return _text_content("\n".join(lines))
```

- [ ] **Step 4: Run search tool tests**

```bash
python -m pytest tests/unit/tools/test_search.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/search.py tests/unit/tools/test_search.py
git commit -m "feat: search tools — get_profile, search, read_message, read_thread"
```

---

### Task 5: Draft Tools — create_draft, update_draft, list_drafts, send_draft

**Files:**
- Create: `src/tools/drafts.py`
- Create: `tests/unit/tools/test_drafts.py`

- [ ] **Step 1: Write draft tool tests**

Create `tests/unit/tools/test_drafts.py`:

```python
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.tools.drafts import (
    handle_create_draft,
    handle_list_drafts,
    handle_send_draft,
    handle_update_draft,
)


class TestCreateDraft:
    def test_creates_draft_returns_id(self) -> None:
        mock_client = MagicMock()
        mock_client.create_draft.return_value = {
            "id": "draft_001",
            "message": {"id": "msg_001"},
        }
        result = handle_create_draft(
            {
                "to": "test@example.com",
                "subject": "Test",
                "body": "Hello",
            },
            mock_client,
        )
        assert "draft_001" in result["content"][0]["text"]
        mock_client.create_draft.assert_called_once()

    def test_with_attachments(self, tmp_path: Any) -> None:
        pdf = tmp_path / "file.pdf"
        pdf.write_bytes(b"pdf content")
        mock_client = MagicMock()
        mock_client.create_draft.return_value = {
            "id": "draft_002",
            "message": {"id": "msg_002"},
        }
        result = handle_create_draft(
            {
                "to": "test@example.com",
                "subject": "With Attachment",
                "body": "See attached",
                "attachments": [{"type": "file", "path": str(pdf)}],
            },
            mock_client,
        )
        call_kwargs = mock_client.create_draft.call_args
        assert call_kwargs.kwargs.get("attachments") or call_kwargs[1].get("attachments")

    def test_body_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="body is required"):
            handle_create_draft({"to": "test@example.com"}, mock_client)


class TestUpdateDraft:
    def test_updates_existing_draft(self) -> None:
        mock_client = MagicMock()
        mock_client.update_draft.return_value = {
            "id": "draft_001",
            "message": {"id": "msg_001"},
        }
        result = handle_update_draft(
            {"draftId": "draft_001", "body": "Updated body"},
            mock_client,
        )
        assert "draft_001" in result["content"][0]["text"]

    def test_draft_id_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="draftId is required"):
            handle_update_draft({"body": "test"}, mock_client)


class TestListDrafts:
    def test_returns_draft_list(self) -> None:
        mock_client = MagicMock()
        mock_client.list_drafts.return_value = {
            "drafts": [{"id": "d1"}, {"id": "d2"}],
            "nextPageToken": None,
        }
        result = handle_list_drafts({}, mock_client)
        text = result["content"][0]["text"]
        assert "d1" in text
        assert "d2" in text


class TestSendDraft:
    def test_sends_draft_returns_confirmation(self) -> None:
        mock_client = MagicMock()
        mock_client.send_draft.return_value = {
            "id": "msg_sent",
            "labelIds": ["SENT"],
        }
        result = handle_send_draft({"draftId": "draft_001"}, mock_client)
        assert "msg_sent" in result["content"][0]["text"]

    def test_draft_id_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="draftId is required"):
            handle_send_draft({}, mock_client)
```

- [ ] **Step 2: Implement draft tools**

Create `src/tools/drafts.py`:

```python
from __future__ import annotations

import json
from typing import Any

from ..gmail_client import GmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def handle_create_draft(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
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
        f"Draft created.\n"
        f"Draft ID: {result['id']}\n"
        f"Message ID: {result['message']['id']}\n"
        f"Use gmail_send_draft with draftId '{result['id']}' to send."
    )


def handle_update_draft(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
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
    return _text_content(
        f"Draft updated.\nDraft ID: {result['id']}"
    )


def handle_list_drafts(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    result = client.list_drafts(
        max_results=args.get("maxResults", 20),
        page_token=args.get("pageToken"),
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


def handle_send_draft(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    draft_id = args.get("draftId")
    if not draft_id:
        raise ValueError("draftId is required")
    result = client.send_draft(draft_id)
    return _text_content(
        f"Draft sent successfully.\n"
        f"Message ID: {result['id']}\n"
        f"Labels: {', '.join(result.get('labelIds', []))}"
    )
```

- [ ] **Step 3: Run draft tests**

```bash
python -m pytest tests/unit/tools/test_drafts.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/drafts.py tests/unit/tools/test_drafts.py
git commit -m "feat: draft tools — create, update, list, send draft"
```

---

### Task 6: Send Tool + Attachment Download + Label Tools

**Files:**
- Create: `src/tools/send.py`, `src/tools/attachments.py`, `src/tools/labels.py`
- Create: `tests/unit/tools/test_send.py`, `tests/unit/tools/test_attachments.py`, `tests/unit/tools/test_labels.py`

- [ ] **Step 1: Write send tool test**

Create `tests/unit/tools/test_send.py`:

```python
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.tools.send import handle_send_email


class TestSendEmail:
    def test_sends_email(self) -> None:
        mock_client = MagicMock()
        mock_client.send_email.return_value = {
            "id": "msg_sent",
            "labelIds": ["SENT"],
        }
        result = handle_send_email(
            {
                "to": "test@example.com",
                "subject": "Test",
                "body": "Hello",
            },
            mock_client,
        )
        assert "msg_sent" in result["content"][0]["text"]

    def test_to_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="to is required"):
            handle_send_email({"body": "hello"}, mock_client)

    def test_body_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="body is required"):
            handle_send_email({"to": "test@example.com"}, mock_client)
```

- [ ] **Step 2: Write attachment download test**

Create `tests/unit/tools/test_attachments.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.tools.attachments import handle_download_attachment


class TestDownloadAttachment:
    def test_downloads_and_saves(self, tmp_path: object) -> None:
        mock_client = MagicMock()
        save = f"{tmp_path}/out.pdf"
        mock_client.download_attachment.return_value = save
        result = handle_download_attachment(
            {
                "messageId": "msg_001",
                "attachmentId": "att_001",
                "savePath": save,
            },
            mock_client,
        )
        assert save in result["content"][0]["text"]

    def test_message_id_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="messageId is required"):
            handle_download_attachment(
                {"attachmentId": "a", "savePath": "/tmp/x"}, mock_client
            )

    def test_attachment_id_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="attachmentId is required"):
            handle_download_attachment(
                {"messageId": "m", "savePath": "/tmp/x"}, mock_client
            )

    def test_save_path_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="savePath is required"):
            handle_download_attachment(
                {"messageId": "m", "attachmentId": "a"}, mock_client
            )
```

- [ ] **Step 3: Write label tool tests**

Create `tests/unit/tools/test_labels.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.tools.labels import handle_list_labels, handle_modify_thread_labels


class TestListLabels:
    def test_returns_labels(self) -> None:
        mock_client = MagicMock()
        mock_client.list_labels.return_value = [
            {"id": "INBOX", "name": "INBOX", "type": "system"},
            {"id": "Label_1", "name": "Important", "type": "user"},
        ]
        result = handle_list_labels({}, mock_client)
        text = result["content"][0]["text"]
        assert "INBOX" in text
        assert "Important" in text


class TestModifyThreadLabels:
    def test_modifies_labels(self) -> None:
        mock_client = MagicMock()
        mock_client.modify_thread_labels.return_value = {"id": "t1"}
        result = handle_modify_thread_labels(
            {
                "threadId": "t1",
                "addLabelIds": ["Label_1"],
                "removeLabelIds": ["INBOX"],
            },
            mock_client,
        )
        assert "t1" in result["content"][0]["text"]

    def test_thread_id_required(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="threadId is required"):
            handle_modify_thread_labels({}, mock_client)
```

- [ ] **Step 4: Implement send tool**

Create `src/tools/send.py`:

```python
from __future__ import annotations

from typing import Any

from ..gmail_client import GmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def handle_send_email(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    to = args.get("to")
    if not to:
        raise ValueError("to is required")
    body = args.get("body")
    if not body:
        raise ValueError("body is required")
    result = client.send_email(
        to=to,
        subject=args.get("subject", ""),
        body=body,
        content_type=args.get("contentType", "text/plain"),
        cc=args.get("cc"),
        bcc=args.get("bcc"),
        attachments=args.get("attachments"),
    )
    return _text_content(
        f"Email sent successfully.\n"
        f"Message ID: {result['id']}\n"
        f"Labels: {', '.join(result.get('labelIds', []))}"
    )
```

- [ ] **Step 5: Implement attachment download tool**

Create `src/tools/attachments.py`:

```python
from __future__ import annotations

from typing import Any

from ..gmail_client import GmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def handle_download_attachment(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    message_id = args.get("messageId")
    if not message_id:
        raise ValueError("messageId is required")
    attachment_id = args.get("attachmentId")
    if not attachment_id:
        raise ValueError("attachmentId is required")
    save_path = args.get("savePath")
    if not save_path:
        raise ValueError("savePath is required")

    saved = client.download_attachment(message_id, attachment_id, save_path)
    return _text_content(f"Attachment saved to: {saved}")
```

- [ ] **Step 6: Implement label tools**

Create `src/tools/labels.py`:

```python
from __future__ import annotations

import json
from typing import Any

from ..gmail_client import GmailClient


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def handle_list_labels(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    labels = client.list_labels()
    lines = [f"Found {len(labels)} labels:"]
    for label in labels:
        lines.append(
            f"  - {label['name']} (id: {label['id']}, type: {label.get('type', 'unknown')})"
        )
    return _text_content("\n".join(lines))


def handle_modify_thread_labels(
    args: dict[str, Any], client: GmailClient
) -> dict[str, Any]:
    thread_id = args.get("threadId")
    if not thread_id:
        raise ValueError("threadId is required")
    result = client.modify_thread_labels(
        thread_id=thread_id,
        add_label_ids=args.get("addLabelIds"),
        remove_label_ids=args.get("removeLabelIds"),
    )
    return _text_content(f"Labels modified for thread: {result['id']}")
```

- [ ] **Step 7: Run all new tests**

```bash
python -m pytest tests/unit/tools/test_send.py tests/unit/tools/test_attachments.py tests/unit/tools/test_labels.py -v
```

Expected: All 10 tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/tools/send.py src/tools/attachments.py src/tools/labels.py tests/unit/tools/test_send.py tests/unit/tools/test_attachments.py tests/unit/tools/test_labels.py
git commit -m "feat: send, attachment download, and label tools"
```

---

### Task 7: Template Tools — save_template, use_template

**Files:**
- Create: `src/tools/templates.py`
- Create: `tests/unit/tools/test_templates.py`

- [ ] **Step 1: Write template tool tests**

Create `tests/unit/tools/test_templates.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.tools.templates import handle_save_template, handle_use_template


class TestSaveTemplate:
    def test_saves_template_file(self, tmp_template_dir: Path) -> None:
        result = handle_save_template(
            {
                "name": "test_template",
                "subject": "Hello {{name}}",
                "body": "Dear {{name}}, your order {{order_id}} is ready.",
                "contentType": "text/plain",
                "variables": ["name", "order_id"],
            },
            MagicMock(),
            template_dir=tmp_template_dir,
        )
        assert "saved" in result["content"][0]["text"].lower()
        saved = json.loads((tmp_template_dir / "test_template.json").read_text())
        assert saved["name"] == "test_template"
        assert saved["variables"] == ["name", "order_id"]

    def test_name_required(self, tmp_template_dir: Path) -> None:
        with pytest.raises(ValueError, match="name is required"):
            handle_save_template(
                {"body": "test"}, MagicMock(), template_dir=tmp_template_dir
            )

    def test_validates_placeholders_match_variables(
        self, tmp_template_dir: Path
    ) -> None:
        with pytest.raises(ValueError, match="not declared in variables"):
            handle_save_template(
                {
                    "name": "bad",
                    "subject": "Hello {{name}}",
                    "body": "Dear {{name}}, {{missing_var}}",
                    "variables": ["name"],
                },
                MagicMock(),
                template_dir=tmp_template_dir,
            )


class TestUseTemplate:
    def test_renders_template_creates_draft(self, tmp_template_dir: Path) -> None:
        tpl = {
            "name": "claim",
            "subject": "Claim for {{policy}}",
            "body": "Dear {{name}}, policy {{policy}}",
            "contentType": "text/plain",
            "variables": ["name", "policy"],
        }
        (tmp_template_dir / "claim.json").write_text(json.dumps(tpl))

        mock_client = MagicMock()
        mock_client.create_draft.return_value = {
            "id": "draft_001",
            "message": {"id": "msg_001"},
        }
        result = handle_use_template(
            {
                "name": "claim",
                "variables": {"name": "Jon", "policy": "12345"},
                "to": "claims@example.com",
            },
            mock_client,
            template_dir=tmp_template_dir,
        )
        call_args = mock_client.create_draft.call_args
        assert "Jon" in call_args.kwargs["body"]
        assert "12345" in call_args.kwargs["subject"]
        assert "draft_001" in result["content"][0]["text"]

    def test_template_not_found_raises(self, tmp_template_dir: Path) -> None:
        with pytest.raises(ValueError, match="Template not found"):
            handle_use_template(
                {"name": "nonexistent", "variables": {}},
                MagicMock(),
                template_dir=tmp_template_dir,
            )

    def test_missing_variable_raises(self, tmp_template_dir: Path) -> None:
        tpl = {
            "name": "test",
            "subject": "{{greeting}}",
            "body": "{{greeting}} {{name}}",
            "contentType": "text/plain",
            "variables": ["greeting", "name"],
        }
        (tmp_template_dir / "test.json").write_text(json.dumps(tpl))
        with pytest.raises(ValueError, match="Missing variables"):
            handle_use_template(
                {"name": "test", "variables": {"greeting": "Hi"}},
                MagicMock(),
                template_dir=tmp_template_dir,
            )
```

- [ ] **Step 2: Implement template tools**

Create `src/tools/templates.py`:

```python
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..gmail_client import GmailClient

DEFAULT_TEMPLATE_DIR = Path("templates")


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _find_placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{\{(\w+)\}\}", text))


def handle_save_template(
    args: dict[str, Any],
    client: GmailClient,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        raise ValueError("name is required")

    subject = args.get("subject", "")
    body = args.get("body", "")
    variables = args.get("variables", [])

    all_placeholders = _find_placeholders(subject) | _find_placeholders(body)
    declared = set(variables)
    undeclared = all_placeholders - declared
    if undeclared:
        raise ValueError(
            f"Placeholders {undeclared} not declared in variables list"
        )

    template = {
        "name": name,
        "subject": subject,
        "body": body,
        "contentType": args.get("contentType", "text/plain"),
        "variables": variables,
    }

    template_dir.mkdir(parents=True, exist_ok=True)
    path = template_dir / f"{name}.json"
    path.write_text(json.dumps(template, indent=2))
    return _text_content(f"Template '{name}' saved to {path}")


def handle_use_template(
    args: dict[str, Any],
    client: GmailClient,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        raise ValueError("name is required")

    path = template_dir / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Template not found: {name}")

    template = json.loads(path.read_text())
    variables = args.get("variables", {})

    required = set(template.get("variables", []))
    provided = set(variables.keys())
    missing = required - provided
    if missing:
        raise ValueError(f"Missing variables: {missing}")

    subject = template.get("subject", "")
    body = template.get("body", "")
    for key, value in variables.items():
        subject = subject.replace(f"{{{{{key}}}}}", value)
        body = body.replace(f"{{{{{key}}}}}", value)

    result = client.create_draft(
        to=args.get("to"),
        subject=subject,
        body=body,
        content_type=template.get("contentType", "text/plain"),
        cc=args.get("cc"),
        bcc=args.get("bcc"),
        attachments=args.get("attachments"),
    )
    return _text_content(
        f"Draft created from template '{name}'.\n"
        f"Draft ID: {result['id']}\n"
        f"Use gmail_send_draft with draftId '{result['id']}' to send."
    )
```

- [ ] **Step 3: Run template tests**

```bash
python -m pytest tests/unit/tools/test_templates.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/templates.py tests/unit/tools/test_templates.py
git commit -m "feat: template tools — save and use with variable substitution"
```

---

### Task 8: Tool Registration + JSON Schemas

**Files:**
- Modify: `src/tools/__init__.py`
- Modify: `src/protocol.py`
- Create: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write tool registry integration test**

Create `tests/unit/test_tool_registry.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from src.tools import ToolRegistry


class TestToolRegistryIntegration:
    def test_all_14_tools_registered(self) -> None:
        mock_client = MagicMock()
        registry = ToolRegistry(gmail_client=mock_client)
        tools = registry.list_tools()
        tool_names = {t["name"] for t in tools}
        expected = {
            "gmail_get_profile",
            "gmail_search_messages",
            "gmail_read_message",
            "gmail_read_thread",
            "gmail_download_attachment",
            "gmail_create_draft",
            "gmail_update_draft",
            "gmail_list_drafts",
            "gmail_send_draft",
            "gmail_send_email",
            "gmail_list_labels",
            "gmail_modify_thread_labels",
            "gmail_save_template",
            "gmail_use_template",
        }
        assert tool_names == expected

    def test_all_tools_have_input_schema(self) -> None:
        mock_client = MagicMock()
        registry = ToolRegistry(gmail_client=mock_client)
        for tool in registry.list_tools():
            assert "inputSchema" in tool, f"{tool['name']} missing inputSchema"
            assert tool["inputSchema"]["type"] == "object"

    def test_execute_unknown_tool_raises(self) -> None:
        from src.models import ToolCallParams

        mock_client = MagicMock()
        registry = ToolRegistry(gmail_client=mock_client)
        import pytest

        with pytest.raises(ValueError, match="Unknown tool"):
            registry.execute_tool(ToolCallParams(name="fake_tool"))
```

- [ ] **Step 2: Update tool registry with all registrations and schemas**

Replace `src/tools/__init__.py`:

```python
from __future__ import annotations

from typing import Any

from loguru import logger

from ..gmail_client import GmailClient
from ..models import ToolCallParams
from .attachments import handle_download_attachment
from .drafts import (
    handle_create_draft,
    handle_list_drafts,
    handle_send_draft,
    handle_update_draft,
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

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "gmail_get_profile",
        "description": "Get Gmail account profile information including email address and message counts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "gmail_search_messages",
        "description": "Search Gmail using full Gmail search syntax (from:, to:, subject:, is:unread, has:attachment, date ranges, etc). Returns message IDs for use with gmail_read_message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Gmail search query"},
                "maxResults": {"type": "integer", "default": 20, "description": "Max results (1-500)"},
                "pageToken": {"type": "string", "description": "Pagination token"},
                "includeSpamTrash": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "gmail_read_message",
        "description": "Read a full email message by ID, including headers, body, and attachment metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageId": {"type": "string", "description": "Message ID from gmail_search_messages"},
            },
            "required": ["messageId"],
        },
    },
    {
        "name": "gmail_read_thread",
        "description": "Read an entire email thread (all messages in a conversation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string", "description": "Thread ID"},
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "gmail_download_attachment",
        "description": "Download an email attachment to a local file path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageId": {"type": "string", "description": "Message ID containing the attachment"},
                "attachmentId": {"type": "string", "description": "Attachment ID from gmail_read_message"},
                "savePath": {"type": "string", "description": "Local file path to save the attachment"},
            },
            "required": ["messageId", "attachmentId", "savePath"],
        },
    },
    {
        "name": "gmail_create_draft",
        "description": "Create an email draft with optional file attachments. Supports local files, Gmail attachments from other emails, and URL downloads. ALWAYS create a draft first and let the user review before sending.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient(s), comma-separated"},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Email body (plain text or HTML)"},
                "cc": {"type": "string"},
                "bcc": {"type": "string"},
                "contentType": {"type": "string", "enum": ["text/plain", "text/html"], "default": "text/plain"},
                "threadId": {"type": "string", "description": "Thread ID to reply to"},
                "attachments": {
                    "type": "array",
                    "description": "File attachments",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["file", "gmail", "url"]},
                            "path": {"type": "string", "description": "Local file path (type=file)"},
                            "messageId": {"type": "string", "description": "Source message ID (type=gmail)"},
                            "attachmentId": {"type": "string", "description": "Source attachment ID (type=gmail)"},
                            "url": {"type": "string", "description": "URL to download (type=url)"},
                            "filename": {"type": "string", "description": "Filename for URL downloads (type=url)"},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["body"],
        },
    },
    {
        "name": "gmail_update_draft",
        "description": "Update an existing draft with new content or attachments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "draftId": {"type": "string", "description": "Draft ID to update"},
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "string"},
                "bcc": {"type": "string"},
                "contentType": {"type": "string", "enum": ["text/plain", "text/html"], "default": "text/plain"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["draftId"],
        },
    },
    {
        "name": "gmail_list_drafts",
        "description": "List all saved email drafts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "maxResults": {"type": "integer", "default": 20},
                "pageToken": {"type": "string"},
            },
        },
    },
    {
        "name": "gmail_send_draft",
        "description": "Send an existing draft by its draft ID. IMPORTANT: Always let the user review the draft in Gmail before sending. Never send without explicit user approval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "draftId": {"type": "string", "description": "Draft ID to send"},
            },
            "required": ["draftId"],
        },
    },
    {
        "name": "gmail_send_email",
        "description": "Send an email directly with optional attachments. IMPORTANT: Always confirm with the user before sending. Prefer creating a draft first with gmail_create_draft for review.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient(s)"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "string"},
                "bcc": {"type": "string"},
                "contentType": {"type": "string", "enum": ["text/plain", "text/html"], "default": "text/plain"},
                "attachments": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["to", "body"],
        },
    },
    {
        "name": "gmail_list_labels",
        "description": "List all Gmail labels (system and user-created).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "gmail_modify_thread_labels",
        "description": "Add or remove labels from an email thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string"},
                "addLabelIds": {"type": "array", "items": {"type": "string"}},
                "removeLabelIds": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["threadId"],
        },
    },
    {
        "name": "gmail_save_template",
        "description": "Save a reusable email template with {{variable}} placeholders.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "contentType": {"type": "string", "enum": ["text/plain", "text/html"], "default": "text/plain"},
                "variables": {"type": "array", "items": {"type": "string"}, "description": "List of variable names used in subject/body"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "gmail_use_template",
        "description": "Render a saved template with variables and create a draft for review. Never sends directly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name"},
                "variables": {"type": "object", "description": "Key-value pairs for template variables"},
                "to": {"type": "string"},
                "cc": {"type": "string"},
                "bcc": {"type": "string"},
                "attachments": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["name", "variables"],
        },
    },
]


class ToolRegistry:
    def __init__(self, gmail_client: GmailClient | None = None) -> None:
        self._client = gmail_client
        self._handlers: dict[str, Any] = {
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

    def list_tools(self) -> list[dict[str, Any]]:
        return TOOL_DEFINITIONS

    def execute_tool(self, params: ToolCallParams) -> dict[str, Any]:
        handler = self._handlers.get(params.name)
        if handler is None:
            raise ValueError(f"Unknown tool: {params.name}")
        logger.info(f"Executing tool: {params.name}")
        return handler(params.arguments, self._client)
```

- [ ] **Step 3: Update protocol to pass gmail_client**

Update `src/protocol.py` — change `__init__` to accept and pass gmail_client:

```python
# In __init__, change:
def __init__(self) -> None:
    from .config import Config
    from .gmail_client import GmailClient

    cfg = Config()
    client = GmailClient(cfg)
    self.tool_registry = ToolRegistry(gmail_client=client)
    self.initialized = False
```

- [ ] **Step 4: Run registry tests**

```bash
python -m pytest tests/unit/test_tool_registry.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/__init__.py src/protocol.py tests/unit/test_tool_registry.py
git commit -m "feat: register all 14 tools with JSON schemas"
```

---

### Task 9: Integration Test — Stdio Roundtrip

**Files:**
- Create: `tests/integration/test_stdio_roundtrip.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_stdio_roundtrip.py`:

```python
from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

from src.protocol import ProtocolHandler
from src.server import StdioServer


def _roundtrip(request: dict[str, Any]) -> dict[str, Any]:
    with patch("src.protocol.GmailClient") as mock_cls, \
         patch("src.protocol.Config"):
        mock_client = MagicMock()
        mock_client.get_profile.return_value = {
            "emailAddress": "test@gmail.com",
            "messagesTotal": 100,
        }
        mock_client.search_messages.return_value = {
            "messages": [{"id": "m1", "threadId": "t1"}],
            "nextPageToken": None,
            "resultSizeEstimate": 1,
        }
        mock_cls.return_value = mock_client

        handler = ProtocolHandler()
        server = StdioServer()
        server._stdin = io.StringIO(json.dumps(request) + "\n")
        output = io.StringIO()
        server._stdout = output
        server.run(handler.handle_request)
        lines = output.getvalue().strip().split("\n")
        return json.loads(lines[-1]) if lines and lines[-1] else {}


class TestStdioRoundtrip:
    def test_initialize(self) -> None:
        resp = _roundtrip(
            {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
                "id": 1,
            }
        )
        assert resp["result"]["serverInfo"]["name"] == "gmail-enhanced-mcp"

    def test_tools_list_returns_14_tools(self) -> None:
        resp = _roundtrip(
            {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2}
        )
        assert len(resp["result"]["tools"]) == 14

    def test_tool_call_get_profile(self) -> None:
        resp = _roundtrip(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "gmail_get_profile", "arguments": {}},
                "id": 3,
            }
        )
        assert "test@gmail.com" in resp["result"]["content"][0]["text"]

    def test_unknown_method_returns_error(self) -> None:
        resp = _roundtrip(
            {"jsonrpc": "2.0", "method": "fake/method", "id": 4}
        )
        assert resp["error"]["code"] == -32601
```

- [ ] **Step 2: Run integration tests**

```bash
python -m pytest tests/integration/test_stdio_roundtrip.py -v
```

Expected: All 4 tests PASS

- [ ] **Step 3: Run full test suite with coverage**

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing -v
```

Expected: All tests PASS, coverage ≥ 90%

- [ ] **Step 4: Commit**

```bash
git add tests/integration/
git commit -m "feat: integration tests — stdio roundtrip with all tools"
```

---

### Task 10: MCP Registration + Final Wiring

**Files:**
- Create: `.mcp.json`
- Verify: `package.json`, `gmail_mcp/__main__.py`

- [ ] **Step 1: Create .mcp.json for Claude Code**

Create `.mcp.json`:

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

- [ ] **Step 2: Run ruff and mypy**

```bash
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python -m mypy src/ --strict 2>&1 | head -50
```

Fix any issues found.

- [ ] **Step 3: Run full test suite one final time**

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing -v
```

Expected: All tests PASS, coverage ≥ 90%

- [ ] **Step 4: Commit final wiring**

```bash
git add .mcp.json
git commit -m "feat: MCP server config for Claude Code registration"
```

---

## Post-Implementation Checklist

- [ ] All 14 tools registered and tested
- [ ] MIME attachments work for file, gmail, and url sources
- [ ] Template save/use working with variable substitution
- [ ] Stdio JSON-RPC roundtrip passes end-to-end
- [ ] Coverage ≥ 90%
- [ ] ruff check clean
- [ ] mypy --strict clean (with Google API stubs exempted)
- [ ] No credentials in git history
- [ ] OAuth auth flow documented in README
