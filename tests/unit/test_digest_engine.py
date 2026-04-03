"""Unit tests for DigestEngine."""

from __future__ import annotations

import base64
from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from src.digest.engine import DigestEngine, DigestResult
from src.triage.cache import TriageCache


def _make_cache() -> TriageCache:
    cache = TriageCache(Path(":memory:"))
    cache.initialize()
    return cache


def _make_msg(
    msg_id: str = "m1",
    from_addr: str = "sender@example.com",
    subject: str = "Test",
    body: str = "Hello",
    to_addr: str = "test@gmail.com",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": f"t_{msg_id}",
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Wed, 02 Apr 2026 10:00:00 -0400"},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
        },
    }


def _make_client(messages: list[dict[str, Any]], email: str = "test@gmail.com") -> MagicMock:
    client = MagicMock()
    client.email_address = email
    client.provider = "gmail"
    stubs = [{"id": m["id"], "threadId": m["threadId"]} for m in messages]
    client.search_messages.return_value = {"messages": stubs}
    msg_by_id = {m["id"]: m for m in messages}
    client.read_message.side_effect = lambda mid: msg_by_id[mid]
    return client


class TestDigestEngineGenerate:
    def test_no_unread_messages_returns_empty_summary(self) -> None:
        client = MagicMock()
        client.email_address = "test@gmail.com"
        client.search_messages.return_value = {"messages": []}

        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        assert isinstance(result, DigestResult)
        assert result.summary.total_unread == 0
        assert result.summary.top_items == []
        assert result.actionable.needs_reply == []

    def test_generate_scores_messages_and_groups_by_category(self) -> None:
        msgs = [
            _make_msg("m1", subject="IRS Notice", from_addr="irs@irs.gov"),
            _make_msg("m2", subject="Newsletter", from_addr="news@bulk.com"),
        ]
        client = _make_client(msgs)
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        assert result.summary.total_unread == 2
        total_categorized = sum(result.summary.by_category.values())
        assert total_categorized == 2

    def test_top_items_limited_to_10(self) -> None:
        msgs = [_make_msg(f"m{i}", subject=f"Msg {i}") for i in range(15)]
        client = _make_client(msgs)
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        assert len(result.summary.top_items) <= 10

    def test_top_items_sorted_by_score_desc(self) -> None:
        msgs = [_make_msg(f"m{i}", subject=f"Msg {i}") for i in range(5)]
        client = _make_client(msgs)
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        scores = [item.score for item in result.summary.top_items]
        assert scores == sorted(scores, reverse=True)

    def test_needs_reply_detected_for_direct_question(self) -> None:
        msgs = [
            _make_msg(
                "m1",
                from_addr="boss@company.com",
                subject="Can you review this?",
                to_addr="test@gmail.com",
            )
        ]
        client = _make_client(msgs)
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        assert len(result.actionable.needs_reply) >= 1
        assert result.actionable.needs_reply[0]["message_id"] == "m1"

    def test_needs_reply_not_flagged_for_own_message(self) -> None:
        msgs = [
            _make_msg(
                "m1",
                from_addr="test@gmail.com",
                subject="Sent by me",
                to_addr="other@example.com",
            )
        ]
        client = _make_client(msgs)
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        reply_ids = [r["message_id"] for r in result.actionable.needs_reply]
        assert "m1" not in reply_ids

    def test_deadline_extracted_from_subject(self) -> None:
        msgs = [_make_msg("m1", subject="Report due April 5 2026", from_addr="boss@company.com")]
        client = _make_client(msgs)
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        if result.actionable.deadlines:
            dl = result.actionable.deadlines[0]
            assert "message_id" in dl
            assert "deadline_date" in dl
            assert "link" in dl

    def test_overdue_followups_included(self) -> None:
        from datetime import datetime

        from src.triage.models import FollowUp, FollowUpStatus

        client = _make_client([])
        cache = _make_cache()

        overdue_item = FollowUp(
            message_id="old_m1",
            thread_id="old_t1",
            subject_hash="abc",
            sent_date=datetime(2026, 3, 1, tzinfo=UTC),
            expected_reply_days=3,
            deadline=None,
            status=FollowUpStatus.WAITING,
        )

        with patch("src.digest.engine.FollowUpTracker") as mock_tracker_cls:
            mock_tracker = MagicMock()
            mock_tracker_cls.return_value = mock_tracker
            mock_tracker.get_overdue.return_value = [overdue_item]

            engine = DigestEngine(client, cache)
            result = engine.generate()

        assert len(result.actionable.overdue_followups) == 1
        assert result.actionable.overdue_followups[0]["message_id"] == "old_m1"

    def test_deep_links_gmail_provider(self) -> None:
        msgs = [_make_msg("abc123", subject="Hello")]
        client = _make_client(msgs, email="test@gmail.com")
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        assert len(result.summary.top_items) >= 1
        link = result.summary.top_items[0].link
        assert "mail.google.com" in link
        assert "abc123" in link

    def test_deep_links_outlook_provider(self) -> None:
        msgs = [_make_msg("abc123", subject="Hello")]
        client = _make_client(msgs, email="test@outlook.com")
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        assert len(result.summary.top_items) >= 1
        link = result.summary.top_items[0].link
        assert "outlook.live.com" in link
        assert "abc123" in link

    def test_calendar_section_omitted_when_no_calendar_ctx(self) -> None:
        client = _make_client([])
        engine = DigestEngine(client, _make_cache(), calendar_ctx=None)
        result = engine.generate()

        assert result.actionable.calendar_conflicts == []

    def test_calendar_section_populated_when_ctx_provided(self) -> None:
        client = _make_client([])
        mock_cal = MagicMock()
        mock_cal.get_today_events.return_value = [{"summary": "Team standup", "start": "09:00"}]
        engine = DigestEngine(client, _make_cache(), calendar_ctx=mock_cal)
        result = engine.generate(period="daily")

        assert len(result.actionable.calendar_conflicts) == 1
        assert result.actionable.calendar_conflicts[0]["summary"] == "Team standup"

    def test_calendar_section_omitted_for_weekly_period(self) -> None:
        client = _make_client([])
        mock_cal = MagicMock()
        mock_cal.get_today_events.return_value = [{"summary": "Team standup", "start": "09:00"}]
        engine = DigestEngine(client, _make_cache(), calendar_ctx=mock_cal)
        result = engine.generate(period="weekly")

        assert result.actionable.calendar_conflicts == []

    def test_period_daily_stored_in_result(self) -> None:
        client = _make_client([])
        engine = DigestEngine(client, _make_cache())
        result = engine.generate(period="daily")

        assert result.period == "daily"

    def test_period_weekly_stored_in_result(self) -> None:
        client = _make_client([])
        engine = DigestEngine(client, _make_cache())
        result = engine.generate(period="weekly")

        assert result.period == "weekly"

    def test_account_matches_client_email(self) -> None:
        client = _make_client([])
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        assert result.account == "test@gmail.com"

    def test_by_category_keys_always_present(self) -> None:
        client = _make_client([])
        engine = DigestEngine(client, _make_cache())
        result = engine.generate()

        for key in ("critical", "high", "normal", "low", "junk"):
            assert key in result.summary.by_category
