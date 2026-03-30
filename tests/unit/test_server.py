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
