"""Tests for FollowUpTracker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.triage.cache import TriageCache
from src.triage.models import FollowUpStatus
from src.triage.tracker import FollowUpTracker


@pytest.fixture()
def cache() -> TriageCache:
    c = TriageCache(db_path=Path(":memory:"))
    c.initialize()
    return c


@pytest.fixture()
def tracker(cache: TriageCache) -> FollowUpTracker:
    return FollowUpTracker(cache=cache)


def _make_msg(
    msg_id: str = "msg123",
    thread_id: str = "thread456",
    from_addr: str = "jpastore79@gmail.com",
    to_addr: str = "someone@example.com",
    subject: str = "Follow up on our meeting",
    date: str = "Mon, 31 Mar 2026 10:00:00 -0400",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": thread_id,
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date},
            ],
            "body": {"data": ""},
        },
    }


class TestTrack:
    def test_creates_follow_up_with_subject_hash(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg(subject="Meeting follow up")
        fu = tracker.track(msg, account="jpastore79@gmail.com")
        assert fu.subject_hash != "Meeting follow up"
        assert len(fu.subject_hash) == 64  # SHA256 hex

    def test_extracts_deadline_from_subject(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg(subject="respond by April 5th")
        fu = tracker.track(msg, account="jpastore79@gmail.com")
        assert fu.deadline is not None
        assert fu.deadline.month == 4
        assert fu.deadline.day == 5

    def test_stores_in_cache(self, tracker: FollowUpTracker, cache: TriageCache) -> None:
        msg = _make_msg()
        account = "jpastore79@gmail.com"
        tracker.track(msg, account=account)
        account_hash = TriageCache.hash_address(account)
        rows = cache._execute_read(
            "SELECT * FROM follow_ups WHERE account_hash = ?", (account_hash,)
        )
        assert len(rows) == 1

    def test_default_expected_days(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg()
        fu = tracker.track(msg, account="test@example.com")
        assert fu.expected_reply_days == 3

    def test_custom_expected_days(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg()
        fu = tracker.track(msg, account="test@example.com", expected_days=7)
        assert fu.expected_reply_days == 7

    def test_status_is_waiting(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg()
        fu = tracker.track(msg, account="test@example.com")
        assert fu.status == FollowUpStatus.WAITING


class TestCheckReplies:
    def test_updates_status_to_replied_when_reply_found(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg(from_addr="me@example.com")
        tracker.track(msg, account="me@example.com")

        client = MagicMock()
        client.read_thread.return_value = {
            "messages": [
                {
                    "id": "msg123",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "me@example.com"},
                            {"name": "Date", "value": "Mon, 31 Mar 2026 10:00:00 -0400"},
                        ]
                    },
                },
                {
                    "id": "msg999",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "other@example.com"},
                            {"name": "Date", "value": "Tue, 01 Apr 2026 10:00:00 -0400"},
                        ]
                    },
                },
            ]
        }

        replied = tracker.check_replies(client, account="me@example.com")
        assert len(replied) == 1
        assert replied[0].status == FollowUpStatus.REPLIED

    def test_leaves_status_waiting_when_no_reply(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg(from_addr="me@example.com")
        tracker.track(msg, account="me@example.com")

        client = MagicMock()
        client.read_thread.return_value = {
            "messages": [
                {
                    "id": "msg123",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "me@example.com"},
                            {"name": "Date", "value": "Mon, 31 Mar 2026 10:00:00 -0400"},
                        ]
                    },
                },
            ]
        }

        replied = tracker.check_replies(client, account="me@example.com")
        assert len(replied) == 0


class TestGetOverdue:
    def test_returns_past_window_follow_ups(
        self, tracker: FollowUpTracker, cache: TriageCache
    ) -> None:
        msg = _make_msg(date="Fri, 21 Mar 2026 10:00:00 -0400")
        tracker.track(msg, account="me@example.com", expected_days=3)
        overdue = tracker.get_overdue(account="me@example.com")
        assert len(overdue) == 1

    def test_excludes_non_waiting_follow_ups(
        self, tracker: FollowUpTracker, cache: TriageCache
    ) -> None:
        msg = _make_msg(date="Fri, 21 Mar 2026 10:00:00 -0400")
        tracker.track(msg, account="me@example.com", expected_days=3)
        tracker.dismiss(1)
        overdue = tracker.get_overdue(account="me@example.com")
        assert len(overdue) == 0


class TestGetApproachingDeadline:
    def test_returns_items_within_window(self, tracker: FollowUpTracker) -> None:
        tomorrow = datetime.now(tz=UTC) + timedelta(days=1)
        deadline_str = tomorrow.strftime("%Y-%m-%d")
        msg = _make_msg(subject=f"deadline: {deadline_str}")
        tracker.track(msg, account="me@example.com")
        approaching = tracker.get_approaching_deadline(account="me@example.com", within_days=2)
        assert len(approaching) == 1

    def test_excludes_items_outside_window(self, tracker: FollowUpTracker) -> None:
        far_future = datetime.now(tz=UTC) + timedelta(days=30)
        deadline_str = far_future.strftime("%Y-%m-%d")
        msg = _make_msg(subject=f"deadline: {deadline_str}")
        tracker.track(msg, account="me@example.com")
        approaching = tracker.get_approaching_deadline(account="me@example.com", within_days=2)
        assert len(approaching) == 0


class TestDismiss:
    def test_sets_status_to_dismissed(self, tracker: FollowUpTracker) -> None:
        msg = _make_msg()
        tracker.track(msg, account="me@example.com")
        tracker.dismiss(1)
        active = tracker.list_active(account="me@example.com")
        assert len(active) == 0


class TestListActive:
    def test_returns_only_waiting_items(self, tracker: FollowUpTracker) -> None:
        msg1 = _make_msg(msg_id="m1")
        msg2 = _make_msg(msg_id="m2")
        tracker.track(msg1, account="me@example.com")
        tracker.track(msg2, account="me@example.com")
        tracker.dismiss(1)
        active = tracker.list_active(account="me@example.com")
        assert len(active) == 1
        assert active[0].message_id == "m2"
