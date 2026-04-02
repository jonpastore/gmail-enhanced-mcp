from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.handler_context import HandlerContext
from src.tools.send import handle_send_email


def _ctx(client=None) -> HandlerContext:
    return HandlerContext(client=client or MagicMock())


class TestSendEmail:
    def test_sends_email(self) -> None:
        mock_client = MagicMock()
        mock_client.send_email.return_value = {"id": "msg_sent", "labelIds": ["SENT"]}
        result = handle_send_email(
            {"to": "test@example.com", "subject": "Test", "body": "Hello"}, _ctx(mock_client)
        )
        assert "msg_sent" in result["content"][0]["text"]

    def test_to_required(self) -> None:
        with pytest.raises(ValueError, match="to is required"):
            handle_send_email({"body": "hello"}, _ctx())

    def test_body_required(self) -> None:
        with pytest.raises(ValueError, match="body is required"):
            handle_send_email({"to": "test@example.com"}, _ctx())
