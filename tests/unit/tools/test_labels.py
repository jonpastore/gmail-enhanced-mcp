from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.handler_context import HandlerContext
from src.tools.labels import handle_list_labels, handle_modify_thread_labels


def _ctx(client=None) -> HandlerContext:
    return HandlerContext(client=client or MagicMock())


class TestListLabels:
    def test_returns_labels(self) -> None:
        mock_client = MagicMock()
        mock_client.list_labels.return_value = [
            {"id": "INBOX", "name": "INBOX", "type": "system"},
            {"id": "Label_1", "name": "Important", "type": "user"},
        ]
        result = handle_list_labels({}, _ctx(mock_client))
        text = result["content"][0]["text"]
        assert "INBOX" in text and "Important" in text


class TestModifyThreadLabels:
    def test_modifies_labels(self) -> None:
        mock_client = MagicMock()
        mock_client.modify_thread_labels.return_value = {"id": "t1"}
        result = handle_modify_thread_labels(
            {"threadId": "t1", "addLabelIds": ["Label_1"], "removeLabelIds": ["INBOX"]},
            _ctx(mock_client),
        )
        assert "t1" in result["content"][0]["text"]

    def test_thread_id_required(self) -> None:
        with pytest.raises(ValueError, match="threadId is required"):
            handle_modify_thread_labels({}, _ctx())
