"""Unit tests for GoogleCalendarContext."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.calendar.context import CalendarEvent, GoogleCalendarContext

tz = ZoneInfo("America/New_York")


def _make_event(
    event_id: str = "evt1",
    summary: str = "Test Meeting",
    attendees: list[str] | None = None,
    event_date: date | None = None,
) -> CalendarEvent:
    d = event_date or date(2026, 4, 2)
    return CalendarEvent(
        event_id=event_id,
        summary=summary,
        start=datetime(d.year, d.month, d.day, 10, 0, tzinfo=tz),
        end=datetime(d.year, d.month, d.day, 11, 0, tzinfo=tz),
        attendee_emails=attendees or ["alice@example.com", "bob@example.com"],
        timezone="America/New_York",
    )


@pytest.fixture()
def mock_client() -> MagicMock:
    client = MagicMock()
    client._user_timezone = "America/New_York"
    return client


@pytest.fixture()
def ctx(mock_client: MagicMock) -> GoogleCalendarContext:
    return GoogleCalendarContext(client=mock_client)


class TestPrimeForDate:
    def test_fetches_events_and_caches_them(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        target = date(2026, 4, 2)
        events = [_make_event()]
        mock_client.list_events.return_value = events

        ctx.prime_for_date(target)

        mock_client.list_events.assert_called_once()
        assert ctx._events_cache[target] == events

    def test_skips_if_already_cached(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        target = date(2026, 4, 2)
        events = [_make_event()]
        mock_client.list_events.return_value = events

        ctx.prime_for_date(target)
        ctx.prime_for_date(target)

        assert mock_client.list_events.call_count == 1

    def test_populates_attendee_set(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        target = date(2026, 4, 2)
        mock_client.list_events.return_value = [
            _make_event(attendees=["Alice@Example.com", "BOB@EXAMPLE.COM"])
        ]

        ctx.prime_for_date(target)

        assert "alice@example.com" in ctx._attendee_set
        assert "bob@example.com" in ctx._attendee_set

    def test_passes_correct_time_range_to_client(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        target = date(2026, 4, 2)
        mock_client.list_events.return_value = []

        ctx.prime_for_date(target)

        _, kwargs = mock_client.list_events.call_args
        assert kwargs["time_min"].date() == target
        assert kwargs["time_max"].date() == target


class TestGetTodayEvents:
    def test_returns_cached_events_for_today(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        today = date.today()
        event = _make_event(event_date=today)
        mock_client.list_events.return_value = [event]

        result = ctx.get_today_events()

        assert result == [event]

    def test_auto_primes_today(self, ctx: GoogleCalendarContext, mock_client: MagicMock) -> None:
        mock_client.list_events.return_value = []

        ctx.get_today_events()

        mock_client.list_events.assert_called_once()


class TestGetEventsForDate:
    def test_returns_events_for_specific_date(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        target = date(2026, 4, 5)
        event = _make_event(event_id="future_evt", event_date=target)
        mock_client.list_events.return_value = [event]

        result = ctx.get_events_for_date(target)

        assert result == [event]

    def test_primes_if_not_cached(self, ctx: GoogleCalendarContext, mock_client: MagicMock) -> None:
        target = date(2026, 4, 5)
        mock_client.list_events.return_value = []

        ctx.get_events_for_date(target)

        mock_client.list_events.assert_called_once()

    def test_returns_empty_list_when_no_events(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        target = date(2026, 4, 5)
        mock_client.list_events.return_value = []

        result = ctx.get_events_for_date(target)

        assert result == []


class TestIsMeetingAttendee:
    def test_returns_true_for_known_attendee(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        today = date.today()
        mock_client.list_events.return_value = [_make_event(attendees=["alice@example.com"])]
        ctx.prime_for_date(today)

        assert ctx.is_meeting_attendee("alice@example.com") is True

    def test_returns_false_for_non_attendee(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        today = date.today()
        mock_client.list_events.return_value = [_make_event(attendees=["alice@example.com"])]
        ctx.prime_for_date(today)

        assert ctx.is_meeting_attendee("stranger@example.com") is False

    def test_case_insensitive_lookup(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        today = date.today()
        mock_client.list_events.return_value = [_make_event(attendees=["Alice@Example.COM"])]
        ctx.prime_for_date(today)

        assert ctx.is_meeting_attendee("ALICE@EXAMPLE.COM") is True

    def test_auto_primes_if_no_cache(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        mock_client.list_events.return_value = []

        ctx.is_meeting_attendee("anyone@example.com")

        mock_client.list_events.assert_called()

    def test_primes_tomorrow_when_hours_ahead_gt_24(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        mock_client.list_events.return_value = []

        ctx.is_meeting_attendee("anyone@example.com", hours_ahead=48)

        assert mock_client.list_events.call_count == 2

    def test_does_not_prime_tomorrow_when_hours_ahead_lte_24(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        mock_client.list_events.return_value = []

        ctx.is_meeting_attendee("anyone@example.com", hours_ahead=24)

        assert mock_client.list_events.call_count == 1

    def test_returns_false_when_cache_populated_but_no_match(
        self, ctx: GoogleCalendarContext, mock_client: MagicMock
    ) -> None:
        today = date.today()
        mock_client.list_events.return_value = []
        ctx.prime_for_date(today)

        assert ctx.is_meeting_attendee("ghost@example.com") is False
