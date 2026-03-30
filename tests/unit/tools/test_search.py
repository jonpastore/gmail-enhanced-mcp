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
    def test_returns_profile_as_text_content(self, sample_profile: dict[str, Any]) -> None:
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
        result = handle_search_messages({"q": "from:test@example.com"}, mock_client)
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
    def test_returns_formatted_message(self, sample_message: dict[str, Any]) -> None:
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
    def test_returns_thread_messages(self, sample_thread: dict[str, Any]) -> None:
        mock_client = MagicMock()
        mock_client.read_thread.return_value = sample_thread
        result = handle_read_thread({"threadId": "thread_001"}, mock_client)
        text = result["content"][0]["text"]
        assert "thread_001" in text

    def test_missing_thread_id_raises(self) -> None:
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="threadId is required"):
            handle_read_thread({}, mock_client)
