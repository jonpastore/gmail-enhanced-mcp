from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.tools.hygiene import (
    handle_block_sender,
    handle_get_unsubscribe_link,
    handle_import_contacts_as_priority,
    handle_list_contacts,
    handle_report_spam,
    handle_trash_messages,
)
from src.triage.cache import TriageCache


def _gmail_client() -> MagicMock:
    client = MagicMock()
    client.provider = "gmail"
    return client


def _outlook_client() -> MagicMock:
    client = MagicMock()
    client.provider = "outlook"
    return client


class TestHandleTrashMessages:
    def test_trash_by_ids(self) -> None:
        client = _gmail_client()
        client.trash_messages.return_value = {"trashed_count": 2, "message_ids": ["a", "b"]}
        result = handle_trash_messages({"messageIds": ["a", "b"]}, client)
        assert "Trashed 2 messages" in result["content"][0]["text"]

    def test_trash_by_query(self) -> None:
        client = _gmail_client()
        client.trash_by_query.return_value = {"trashed_count": 5, "message_ids": ["a"] * 5}
        result = handle_trash_messages({"query": "from:spam"}, client)
        assert "Trashed 5 messages" in result["content"][0]["text"]

    def test_rejects_outlook(self) -> None:
        client = _outlook_client()
        result = handle_trash_messages({"messageIds": ["a"]}, client)
        assert "only available for Gmail" in result["content"][0]["text"]

    def test_requires_ids_or_query(self) -> None:
        client = _gmail_client()
        result = handle_trash_messages({}, client)
        assert "messageIds or query" in result["content"][0]["text"]


class TestHandleBlockSender:
    def test_blocks_sender(self) -> None:
        client = _gmail_client()
        client.create_block_filter.return_value = {"filter_id": "f1", "existing_trashed": 3}
        result = handle_block_sender({"sender": "spam@test.com"}, client)
        text = result["content"][0]["text"]
        assert "spam@test.com" in text
        assert "3" in text

    def test_rejects_outlook(self) -> None:
        client = _outlook_client()
        result = handle_block_sender({"sender": "x"}, client)
        assert "only available for Gmail" in result["content"][0]["text"]

    def test_requires_sender(self) -> None:
        client = _gmail_client()
        result = handle_block_sender({}, client)
        assert "sender is required" in result["content"][0]["text"]


class TestHandleReportSpam:
    def test_reports_spam(self) -> None:
        client = _gmail_client()
        client.report_spam.return_value = {"reported_count": 4}
        result = handle_report_spam({"messageIds": ["a", "b", "c", "d"]}, client)
        assert "4" in result["content"][0]["text"]

    def test_rejects_outlook(self) -> None:
        client = _outlook_client()
        result = handle_report_spam({"messageIds": ["a"]}, client)
        assert "only available for Gmail" in result["content"][0]["text"]

    def test_requires_message_ids(self) -> None:
        client = _gmail_client()
        result = handle_report_spam({}, client)
        assert "messageIds is required" in result["content"][0]["text"]


class TestHandleListContacts:
    def test_lists_contacts(self) -> None:
        client = _gmail_client()
        client.get_contacts.return_value = [
            {"name": "Alice", "emails": ["alice@test.com"]},
        ]
        result = handle_list_contacts({}, client)
        assert "Alice" in result["content"][0]["text"]

    def test_no_contacts(self) -> None:
        client = _gmail_client()
        client.get_contacts.return_value = []
        result = handle_list_contacts({}, client)
        assert "No contacts" in result["content"][0]["text"]


class TestHandleImportContactsAsPriority:
    def test_imports_contacts(self, tmp_path: Any) -> None:
        client = _gmail_client()
        client.get_contacts.return_value = [
            {"name": "Alice", "emails": ["alice@test.com"]},
            {"name": "Bob", "emails": ["bob@test.com"]},
        ]
        cache = TriageCache(tmp_path / "test.db")
        cache.initialize()
        result = handle_import_contacts_as_priority({"tier": "normal"}, client, cache)
        text = result["content"][0]["text"]
        assert "Added: 2" in text
        assert "Skipped (already matched): 0" in text
        cache.close()

    def test_skips_already_matched(self, tmp_path: Any) -> None:
        client = _gmail_client()
        client.get_contacts.return_value = [
            {"name": "Alice", "emails": ["alice@test.com"]},
        ]
        cache = TriageCache(tmp_path / "test.db")
        cache.initialize()
        from src.triage.models import PrioritySender, SenderTier

        cache.add_priority_sender(
            PrioritySender(email_pattern="alice@test.com", tier=SenderTier.HIGH, label="Alice")
        )
        result = handle_import_contacts_as_priority({"tier": "normal"}, client, cache)
        text = result["content"][0]["text"]
        assert "Added: 0" in text
        assert "Skipped (already matched): 1" in text
        cache.close()

    def test_invalid_tier(self, tmp_path: Any) -> None:
        client = _gmail_client()
        cache = TriageCache(tmp_path / "test.db")
        cache.initialize()
        result = handle_import_contacts_as_priority({"tier": "superduper"}, client, cache)
        assert "Invalid tier" in result["content"][0]["text"]
        cache.close()


class TestHandleGetUnsubscribeLink:
    def test_returns_link(self) -> None:
        client = _gmail_client()
        client.extract_unsubscribe_link.return_value = {
            "found": True,
            "unsubscribe_url": "https://example.com/unsub",
            "unsubscribe_mailto": None,
        }
        result = handle_get_unsubscribe_link({"messageId": "msg_001"}, client)
        assert "https://example.com/unsub" in result["content"][0]["text"]

    def test_not_found(self) -> None:
        client = _gmail_client()
        client.extract_unsubscribe_link.return_value = {
            "found": False,
            "unsubscribe_url": None,
            "unsubscribe_mailto": None,
        }
        result = handle_get_unsubscribe_link({"messageId": "msg_001"}, client)
        assert "No unsubscribe" in result["content"][0]["text"]

    def test_requires_message_id(self) -> None:
        client = _gmail_client()
        result = handle_get_unsubscribe_link({}, client)
        assert "messageId is required" in result["content"][0]["text"]
