from __future__ import annotations

from unittest.mock import MagicMock

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
        result = handler.handle_request({"jsonrpc": "2.0", "method": "initialized"})
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
        result = handler.handle_request({"jsonrpc": "2.0", "method": "nonexistent", "id": 3})
        assert result["error"]["code"] == -32601

    def test_tools_call_delegates_to_registry(self) -> None:
        handler = ProtocolHandler.__new__(ProtocolHandler)
        handler.initialized = True
        mock_registry = MagicMock()
        mock_registry.execute_tool.return_value = {"content": [{"type": "text", "text": "result"}]}
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
