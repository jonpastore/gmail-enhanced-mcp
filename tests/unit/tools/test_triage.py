"""Unit tests for triage tool handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from src.handler_context import HandlerContext
from src.triage.cache import TriageCache
from src.triage.models import SenderTier


def _make_cache() -> TriageCache:
    cache = TriageCache(Path(":memory:"))
    cache.initialize()
    return cache


def _ctx(client=None, cache=None) -> HandlerContext:
    return HandlerContext(client=client or MagicMock(), cache=cache or _make_cache())


def _make_message(
    msg_id: str = "msg_001",
    thread_id: str = "thread_001",
    from_addr: str = "sender@example.com",
    to_addr: str = "me@gmail.com",
    subject: str = "Test Email",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 10 Mar 2026 10:00:00 -0500"},
            ],
            "body": {"data": ""},
            "parts": [],
        },
    }


class TestHandleTriageInbox:
    def test_scores_and_returns_results(self) -> None:
        from src.tools.triage import handle_triage_inbox

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {
            "messages": [{"id": "msg_001", "threadId": "t1"}],
        }
        client.read_message.return_value = _make_message()

        result = handle_triage_inbox({}, _ctx(client, cache))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "msg_001" in text
        assert "Score:" in text

    def test_empty_results(self) -> None:
        from src.tools.triage import handle_triage_inbox

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}

        result = handle_triage_inbox({}, _ctx(client, cache))

        assert "No messages found" in result["content"][0]["text"]

    def test_batches_reads_in_groups_of_10(self) -> None:
        from src.tools.triage import handle_triage_inbox

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"
        msgs = [{"id": f"msg_{i:03d}", "threadId": f"t_{i}"} for i in range(15)]
        client.search_messages.return_value = {"messages": msgs}
        client.read_message.side_effect = [
            _make_message(msg_id=f"msg_{i:03d}", thread_id=f"t_{i}") for i in range(15)
        ]

        with patch("src.tools.triage.time.sleep") as mock_sleep:
            result = handle_triage_inbox({"maxResults": 15}, _ctx(client, cache))

        assert not result.get("isError")
        assert mock_sleep.call_count == 1

    def test_custom_query(self) -> None:
        from src.tools.triage import handle_triage_inbox

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}

        handle_triage_inbox({"q": "is:unread"}, _ctx(client, cache))

        client.search_messages.assert_called_once_with(q="is:unread", max_results=20)

    def test_error_handling(self) -> None:
        from src.tools.triage import handle_triage_inbox

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.side_effect = RuntimeError("API down")

        result = handle_triage_inbox({}, _ctx(client, cache))

        assert result["isError"] is True
        assert "RuntimeError" in result["content"][0]["text"]


class TestHandleAddPrioritySender:
    def test_adds_successfully(self) -> None:
        from src.tools.triage import handle_add_priority_sender

        cache = _make_cache()
        client = MagicMock()
        args = {"pattern": "*@irs.gov", "tier": "critical", "label": "Government"}

        result = handle_add_priority_sender(args, _ctx(client, cache))

        assert not result.get("isError")
        assert "*@irs.gov" in result["content"][0]["text"]
        senders = cache.get_priority_senders()
        assert len(senders) == 1
        assert senders[0].tier == SenderTier.CRITICAL

    def test_missing_required_fields(self) -> None:
        from src.tools.triage import handle_add_priority_sender

        cache = _make_cache()
        client = MagicMock()

        result = handle_add_priority_sender({}, _ctx(client, cache))

        assert result["isError"] is True


class TestHandleListPrioritySenders:
    def test_returns_grouped_by_tier(self) -> None:
        from src.tools.triage import handle_add_priority_sender, handle_list_priority_senders

        cache = _make_cache()
        client = MagicMock()
        ctx = _ctx(client, cache)
        handle_add_priority_sender(
            {"pattern": "*@irs.gov", "tier": "critical", "label": "Government"},
            ctx,
        )
        handle_add_priority_sender(
            {"pattern": "boss@work.com", "tier": "high", "label": "Boss"},
            ctx,
        )

        result = handle_list_priority_senders({}, ctx)

        text = result["content"][0]["text"]
        assert "CRITICAL" in text
        assert "HIGH" in text
        assert "*@irs.gov" in text
        assert "boss@work.com" in text

    def test_empty_list(self) -> None:
        from src.tools.triage import handle_list_priority_senders

        cache = _make_cache()
        client = MagicMock()

        result = handle_list_priority_senders({}, _ctx(client, cache))

        assert "No priority senders" in result["content"][0]["text"]


class TestHandleRemovePrioritySender:
    def test_removes_existing(self) -> None:
        from src.tools.triage import (
            handle_add_priority_sender,
            handle_remove_priority_sender,
        )

        cache = _make_cache()
        client = MagicMock()
        ctx = _ctx(client, cache)
        handle_add_priority_sender(
            {"pattern": "*@irs.gov", "tier": "critical", "label": "Gov"},
            ctx,
        )

        result = handle_remove_priority_sender({"pattern": "*@irs.gov"}, ctx)

        assert not result.get("isError")
        assert "Removed" in result["content"][0]["text"]

    def test_not_found(self) -> None:
        from src.tools.triage import handle_remove_priority_sender

        cache = _make_cache()
        client = MagicMock()

        result = handle_remove_priority_sender({"pattern": "nope@x.com"}, _ctx(client, cache))

        assert "not found" in result["content"][0]["text"].lower()


class TestHandleTrackFollowup:
    def test_tracks_message(self) -> None:
        from src.tools.triage import handle_track_followup

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.read_message.return_value = _make_message(msg_id="sent_001", subject="Please review")

        result = handle_track_followup({"messageId": "sent_001"}, _ctx(client, cache))

        assert not result.get("isError")
        assert "sent_001" in result["content"][0]["text"]

    def test_custom_expected_days(self) -> None:
        from src.tools.triage import handle_track_followup

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.read_message.return_value = _make_message(msg_id="sent_002")

        result = handle_track_followup(
            {"messageId": "sent_002", "expectedDays": 7}, _ctx(client, cache)
        )

        assert not result.get("isError")


class TestHandleCheckFollowups:
    def test_returns_structured_report(self) -> None:
        from src.tools.triage import handle_check_followups

        cache = _make_cache()
        client = MagicMock()
        client.email_address = "me@gmail.com"

        result = handle_check_followups({}, _ctx(client, cache))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "Follow-Up Report" in text


class TestHandleResetTriageCache:
    def test_requires_confirm_true(self) -> None:
        from src.tools.triage import handle_reset_triage_cache

        cache = _make_cache()
        client = MagicMock()

        result = handle_reset_triage_cache({"confirm": False}, _ctx(client, cache))

        assert result["isError"] is True
        assert "confirm" in result["content"][0]["text"].lower()

    def test_resets_with_confirm(self) -> None:
        from src.tools.triage import handle_reset_triage_cache

        cache = _make_cache()
        client = MagicMock()

        result = handle_reset_triage_cache({"confirm": True}, _ctx(client, cache))

        assert not result.get("isError")
        assert "reset" in result["content"][0]["text"].lower()
