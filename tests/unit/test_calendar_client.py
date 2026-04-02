from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.calendar.client import GoogleCalendarClient, _parse_event
from src.calendar.context import CalendarEvent

SAMPLE_EVENT = {
    "id": "evt_123",
    "summary": "Team Standup",
    "start": {"dateTime": "2026-04-02T10:00:00-04:00", "timeZone": "America/New_York"},
    "end": {"dateTime": "2026-04-02T10:30:00-04:00", "timeZone": "America/New_York"},
    "attendees": [
        {"email": "alice@example.com"},
        {"email": "bob@example.com"},
    ],
    "location": "Conference Room A",
}

SAMPLE_ALL_DAY_EVENT = {
    "id": "evt_456",
    "summary": "Company Holiday",
    "start": {"date": "2026-04-02"},
    "end": {"date": "2026-04-03"},
}

SAMPLE_FREEBUSY_RESPONSE = {
    "calendars": {
        "primary": {
            "busy": [
                {"start": "2026-04-02T10:00:00Z", "end": "2026-04-02T10:30:00Z"},
            ]
        }
    }
}


@pytest.fixture
def mock_token_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.validate_scopes.return_value = None
    mgr.get_credentials.return_value = MagicMock()
    return mgr


@pytest.fixture
def mock_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_token_manager: MagicMock, mock_service: MagicMock) -> GoogleCalendarClient:
    with patch("src.calendar.client.build", return_value=mock_service):
        cal = GoogleCalendarClient(mock_token_manager)
    cal._service = mock_service
    return cal


class TestGoogleCalendarClientConstructor:
    def test_constructor_calls_validate_scopes_with_calendar_readonly(
        self, mock_token_manager: MagicMock, mock_service: MagicMock
    ) -> None:
        with patch("src.calendar.client.build", return_value=mock_service):
            GoogleCalendarClient(mock_token_manager)
        mock_token_manager.validate_scopes.assert_called_once_with(
            ["https://www.googleapis.com/auth/calendar.readonly"]
        )


class TestListEvents:
    def test_list_events_returns_calendar_event_models(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.events().list().execute.return_value = {"items": [SAMPLE_EVENT]}
        time_min = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        time_max = datetime(2026, 4, 2, 23, 59, tzinfo=UTC)

        result = client.list_events(time_min, time_max)

        assert len(result) == 1
        assert isinstance(result[0], CalendarEvent)
        assert result[0].event_id == "evt_123"
        assert result[0].summary == "Team Standup"

    def test_list_events_handles_empty_results(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.events().list().execute.return_value = {"items": []}
        time_min = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        time_max = datetime(2026, 4, 2, 23, 59, tzinfo=UTC)

        result = client.list_events(time_min, time_max)

        assert result == []

    def test_list_events_handles_missing_items_key(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.events().list().execute.return_value = {}
        time_min = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        time_max = datetime(2026, 4, 2, 23, 59, tzinfo=UTC)

        result = client.list_events(time_min, time_max)

        assert result == []

    def test_list_events_caches_result_on_second_call(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.events().list().execute.return_value = {"items": [SAMPLE_EVENT]}
        time_min = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        time_max = datetime(2026, 4, 2, 23, 59, tzinfo=UTC)

        client.list_events(time_min, time_max)
        client.list_events(time_min, time_max)

        assert mock_service.events().list().execute.call_count == 1

    def test_list_events_cache_expires_after_ttl(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.events().list().execute.return_value = {"items": [SAMPLE_EVENT]}
        time_min = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        time_max = datetime(2026, 4, 2, 23, 59, tzinfo=UTC)

        client.list_events(time_min, time_max)

        cache_key = f"list:primary:{time_min.isoformat()}:{time_max.isoformat()}"
        client._cache[cache_key] = (time.monotonic() - 1.0, client._cache[cache_key][1])

        client.list_events(time_min, time_max)

        assert mock_service.events().list().execute.call_count == 2


class TestGetEvent:
    def test_get_event_returns_single_calendar_event(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.events().get().execute.return_value = SAMPLE_EVENT

        result = client.get_event("evt_123")

        assert isinstance(result, CalendarEvent)
        assert result.event_id == "evt_123"
        assert result.summary == "Team Standup"

    def test_get_event_caches_result(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.events().get().execute.return_value = SAMPLE_EVENT

        client.get_event("evt_123")
        client.get_event("evt_123")

        assert mock_service.events().get().execute.call_count == 1


class TestCheckFreebusy:
    def test_check_freebusy_returns_busy_periods_dict(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.freebusy().query().execute.return_value = SAMPLE_FREEBUSY_RESPONSE
        time_min = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        time_max = datetime(2026, 4, 2, 23, 59, tzinfo=UTC)

        result = client.check_freebusy(time_min, time_max)

        assert "primary" in result
        assert len(result["primary"]) == 1
        start, end = result["primary"][0]
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)

    def test_check_freebusy_defaults_to_primary_calendar(
        self, client: GoogleCalendarClient, mock_service: MagicMock
    ) -> None:
        mock_service.freebusy().query().execute.return_value = SAMPLE_FREEBUSY_RESPONSE
        time_min = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        time_max = datetime(2026, 4, 2, 23, 59, tzinfo=UTC)

        client.check_freebusy(time_min, time_max, calendar_ids=None)

        call_kwargs = mock_service.freebusy().query.call_args
        body = call_kwargs.kwargs["body"]
        assert body["items"] == [{"id": "primary"}]


class TestParseEvent:
    def test_parse_event_handles_timed_event(self) -> None:
        event = _parse_event(SAMPLE_EVENT, "America/New_York")

        assert event.is_all_day is False
        assert event.summary == "Team Standup"
        assert event.timezone == "America/New_York"

    def test_parse_event_handles_all_day_event(self) -> None:
        event = _parse_event(SAMPLE_ALL_DAY_EVENT, "America/New_York")

        assert event.is_all_day is True
        assert event.summary == "Company Holiday"
        assert event.start.date().isoformat() == "2026-04-02"
        assert event.end.date().isoformat() == "2026-04-03"

    def test_parse_event_extracts_attendee_emails(self) -> None:
        event = _parse_event(SAMPLE_EVENT, "America/New_York")

        assert "alice@example.com" in event.attendee_emails
        assert "bob@example.com" in event.attendee_emails

    def test_parse_event_handles_no_attendees(self) -> None:
        raw = {**SAMPLE_EVENT, "attendees": []}
        event = _parse_event(raw, "America/New_York")

        assert event.attendee_emails == []

    def test_parse_event_uses_user_timezone_as_fallback(self) -> None:
        raw = {
            "id": "evt_789",
            "summary": "No TZ Event",
            "start": {"dateTime": "2026-04-02T10:00:00-04:00"},
            "end": {"dateTime": "2026-04-02T11:00:00-04:00"},
        }
        event = _parse_event(raw, "America/Chicago")

        assert event.timezone == "America/Chicago"

    def test_parse_event_extracts_location(self) -> None:
        event = _parse_event(SAMPLE_EVENT, "America/New_York")

        assert event.location == "Conference Room A"

    def test_parse_event_uses_no_title_for_missing_summary(self) -> None:
        raw = {
            "id": "evt_000",
            "start": {"date": "2026-04-02"},
            "end": {"date": "2026-04-03"},
        }
        event = _parse_event(raw, "America/New_York")

        assert event.summary == "(No title)"
