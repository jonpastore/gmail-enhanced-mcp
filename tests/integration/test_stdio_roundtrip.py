from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

from src.protocol import ProtocolHandler
from src.server import StdioServer


def _roundtrip(*requests: dict[str, Any]) -> list[dict[str, Any]]:
    with patch("src.config.Config"), \
         patch("src.gmail_client.GmailClient") as mock_cls:
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
        input_lines = "\n".join(json.dumps(r) for r in requests) + "\n"
        server._stdin = io.StringIO(input_lines)
        output = io.StringIO()
        server._stdout = output
        server.run(handler.handle_request)
        lines = output.getvalue().strip().split("\n")
        return [json.loads(line) for line in lines if line.strip()]


class TestStdioRoundtrip:
    def test_initialize(self) -> None:
        results = _roundtrip({
            "jsonrpc": "2.0", "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}}, "id": 1,
        })
        assert results[0]["result"]["serverInfo"]["name"] == "gmail-enhanced-mcp"

    def test_tools_list_returns_14_tools(self) -> None:
        results = _roundtrip(
            {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2}
        )
        assert len(results[0]["result"]["tools"]) == 14

    def test_tool_call_get_profile(self) -> None:
        results = _roundtrip(
            {
                "jsonrpc": "2.0", "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}}, "id": 1,
            },
            {
                "jsonrpc": "2.0", "method": "tools/call",
                "params": {"name": "gmail_get_profile", "arguments": {}}, "id": 3,
            },
        )
        tool_resp = results[1]
        assert "test@gmail.com" in tool_resp["result"]["content"][0]["text"]

    def test_unknown_method_returns_error(self) -> None:
        results = _roundtrip(
            {"jsonrpc": "2.0", "method": "fake/method", "id": 4}
        )
        assert results[0]["error"]["code"] == -32601
