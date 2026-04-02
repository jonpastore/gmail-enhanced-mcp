"""Tests for calendar-aware scoring in ImportanceScorer."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.triage.cache import TriageCache
from src.triage.engine import ImportanceScorer


@pytest.fixture()
def cache() -> TriageCache:
    c = TriageCache(db_path=Path(":memory:"))
    c.initialize()
    return c


def _make_msg(
    msg_id: str = "msg123",
    thread_id: str = "thread456",
    from_addr: str = "someone@example.com",
    to_addr: str = "jpastore79@gmail.com",
    subject: str = "Test Subject",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 31 Mar 2026 10:00:00 -0400"},
            ],
            "parts": [{"mimeType": "text/plain", "body": {"data": ""}}],
        },
    }


def _make_calendar_ctx(attendees: list[str] | None = None) -> MagicMock:
    ctx = MagicMock()
    attendee_set = {a.lower() for a in (attendees or [])}
    ctx.is_meeting_attendee.side_effect = lambda email, **_kw: email.lower() in attendee_set
    ctx.prime_for_date.return_value = None
    return ctx


class TestScorerWithoutCalendarCtx:
    def test_no_meeting_today_sender_signal_when_ctx_is_none(self, cache: TriageCache) -> None:
        scorer = ImportanceScorer(cache=cache, calendar_ctx=None)
        msg = _make_msg(from_addr="alice@example.com")

        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]

        assert "meeting_today_sender" not in names

    def test_score_messages_no_prime_when_ctx_is_none(self, cache: TriageCache) -> None:
        scorer = ImportanceScorer(cache=cache, calendar_ctx=None)
        msgs = [_make_msg()]

        result = scorer.score_messages(msgs, "jpastore79@gmail.com")

        assert len(result) == 1

    def test_score_deterministic_without_calendar(self, cache: TriageCache) -> None:
        scorer = ImportanceScorer(cache=cache, calendar_ctx=None)
        msg = _make_msg()

        s1 = scorer.score_message(msg, "jpastore79@gmail.com")
        s2 = scorer.score_message(msg, "jpastore79@gmail.com")

        assert s1.score == s2.score
        assert s1.category == s2.category


class TestScorerWithCalendarCtx:
    def test_meeting_today_sender_signal_added_for_attendee(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx(attendees=["alice@example.com"])
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        msg = _make_msg(from_addr="alice@example.com")

        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]

        assert "meeting_today_sender" in names

    def test_no_meeting_today_sender_signal_for_non_attendee(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx(attendees=["alice@example.com"])
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        msg = _make_msg(from_addr="stranger@example.com")

        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]

        assert "meeting_today_sender" not in names

    def test_meeting_today_sender_signal_has_positive_weight(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx(attendees=["alice@example.com"])
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        msg = _make_msg(from_addr="alice@example.com")

        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        meeting_signal = next(s for s in signals if s.name == "meeting_today_sender")

        assert meeting_signal.weight > 0

    def test_meeting_today_sender_signal_weight_matches_config(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx(attendees=["alice@example.com"])
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        msg = _make_msg(from_addr="alice@example.com")

        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        meeting_signal = next(s for s in signals if s.name == "meeting_today_sender")

        assert meeting_signal.weight == scorer._weights["meeting_today_sender"]

    def test_meeting_attendee_scores_higher_than_same_sender_without_ctx(
        self, cache: TriageCache
    ) -> None:
        ctx = _make_calendar_ctx(attendees=["alice@example.com"])
        scorer_with = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        scorer_without = ImportanceScorer(cache=cache, calendar_ctx=None)
        msg = _make_msg(from_addr="alice@example.com")

        score_with = scorer_with.score_message(msg, "jpastore79@gmail.com")
        score_without = scorer_without.score_message(msg, "jpastore79@gmail.com")

        assert score_with.score > score_without.score


class TestScoreMessagesPrimesCalendar:
    def test_prime_for_date_called_once_before_scoring_loop(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx()
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        msgs = [_make_msg(msg_id=f"msg_{i}") for i in range(5)]

        scorer.score_messages(msgs, "jpastore79@gmail.com")

        assert ctx.prime_for_date.call_count == 1

    def test_prime_for_date_called_with_today(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx()
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        msgs = [_make_msg()]

        scorer.score_messages(msgs, "jpastore79@gmail.com")

        ctx.prime_for_date.assert_called_once_with(date.today())

    def test_prime_not_called_when_ctx_is_none(self, cache: TriageCache) -> None:
        scorer = ImportanceScorer(cache=cache, calendar_ctx=None)
        msgs = [_make_msg()]

        scorer.score_messages(msgs, "jpastore79@gmail.com")

    def test_empty_messages_still_primes_calendar(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx()
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)

        scorer.score_messages([], "jpastore79@gmail.com")

        ctx.prime_for_date.assert_called_once_with(date.today())

    def test_results_still_sorted_descending_with_calendar_ctx(self, cache: TriageCache) -> None:
        ctx = _make_calendar_ctx(attendees=["alice@example.com"])
        scorer = ImportanceScorer(cache=cache, calendar_ctx=ctx)
        msgs = [
            _make_msg(msg_id="low", from_addr="newsletter@spam.com"),
            _make_msg(msg_id="high", from_addr="alice@example.com"),
        ]

        results = scorer.score_messages(msgs, "jpastore79@gmail.com")

        assert results[0].message_id == "high"
        assert results[0].score >= results[1].score
