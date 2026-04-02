"""Unit tests for calendar tool handlers."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from src.calendar.context import CalendarEvent
from src.handler_context import HandlerContext
from src.triage.cache import TriageCache

tz = ZoneInfo("America/New_York")


def _make_cache() -> TriageCache:
    cache = TriageCache(Path(":memory:"))
    cache.initialize()
    return cache


def _ctx(client=None, calendar_ctx=None, cache=None) -> HandlerContext:
    return HandlerContext(
        client=client or MagicMock(),
        cache=cache or _make_cache(),
        calendar_ctx=calendar_ctx,
    )


def _make_event(
    event_id: str = "evt1",
    summary: str = "Test Meeting",
    attendees: list[str] | None = None,
    start_offset_hours: float = 1.0,
    is_all_day: bool = False,
) -> CalendarEvent:
    now = datetime.now(tz=tz)
    start = now + timedelta(hours=start_offset_hours)
    end = start + timedelta(hours=1)
    return CalendarEvent(
        event_id=event_id,
        summary=summary,
        start=start,
        end=end,
        attendee_emails=attendees or ["alice@example.com", "bob@example.com"],
        timezone="America/New_York",
        is_all_day=is_all_day,
    )


def _make_message(
    msg_id: str = "msg_001",
    thread_id: str = "thread_001",
    from_addr: str = "sender@example.com",
    subject: str = "Test Email",
    snippet: str = "",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": subject},
            ],
        },
    }


def _make_calendar_ctx(events: list[CalendarEvent] | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.get_today_events.return_value = events or []
    ctx.get_events_for_date.return_value = events or []
    ctx.prime_for_date.return_value = None
    ctx.is_meeting_attendee.return_value = False
    return ctx


class TestHandleCheckEmailConflicts:
    def test_no_messages_returns_no_messages_text(self) -> None:
        from src.tools.calendar import handle_check_email_conflicts

        client = MagicMock()
        client.search_messages.return_value = {"messages": []}
        cal_ctx = _make_calendar_ctx()

        result = handle_check_email_conflicts({}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        assert "No messages" in result["content"][0]["text"]

    def test_finds_conflict_with_date_mention_and_event(self) -> None:
        from src.tools.calendar import handle_check_email_conflicts

        client = MagicMock()
        client.search_messages.return_value = {"messages": [{"id": "msg_001", "threadId": "t1"}]}
        client.read_message.return_value = _make_message(
            msg_id="msg_001",
            subject="Meeting tomorrow",
            snippet="Let's meet tomorrow at the office",
        )
        event = _make_event(summary="Existing Standup")
        cal_ctx = _make_calendar_ctx(events=[event])
        cal_ctx.get_events_for_date.return_value = [event]

        result = handle_check_email_conflicts({"daysAhead": 7}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "conflict" in text.lower() or "No scheduling conflicts" in text

    def test_no_conflicts_returns_no_conflicts_text(self) -> None:
        from src.tools.calendar import handle_check_email_conflicts

        client = MagicMock()
        client.search_messages.return_value = {"messages": [{"id": "msg_001", "threadId": "t1"}]}
        client.read_message.return_value = _make_message(
            msg_id="msg_001",
            subject="Hello there",
            snippet="No dates mentioned here",
        )
        cal_ctx = _make_calendar_ctx(events=[])
        cal_ctx.get_events_for_date.return_value = []

        result = handle_check_email_conflicts({}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        assert "No scheduling conflicts" in result["content"][0]["text"]

    def test_error_handling_returns_error_content(self) -> None:
        from src.tools.calendar import handle_check_email_conflicts

        client = MagicMock()
        client.search_messages.side_effect = RuntimeError("API down")
        cal_ctx = _make_calendar_ctx()

        result = handle_check_email_conflicts({}, _ctx(client, cal_ctx))

        assert result["isError"] is True
        assert "RuntimeError" in result["content"][0]["text"]

    def test_passes_query_to_search(self) -> None:
        from src.tools.calendar import handle_check_email_conflicts

        client = MagicMock()
        client.search_messages.return_value = {"messages": []}
        cal_ctx = _make_calendar_ctx()

        handle_check_email_conflicts({"q": "invoice", "maxResults": 5}, _ctx(client, cal_ctx))

        client.search_messages.assert_called_once_with(q="invoice", max_results=5)

    def test_no_calendar_ctx_returns_error(self) -> None:
        from src.tools.calendar import handle_check_email_conflicts

        client = MagicMock()
        result = handle_check_email_conflicts({}, _ctx(client, None))
        assert result["isError"] is True
        assert "Calendar not configured" in result["content"][0]["text"]


class TestHandleMeetingPrep:
    def test_no_events_returns_no_meetings_text(self) -> None:
        from src.tools.calendar import handle_meeting_prep

        client = MagicMock()
        cal_ctx = _make_calendar_ctx(events=[])

        result = handle_meeting_prep({}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        assert "No meetings found today" in result["content"][0]["text"]

    def test_upcoming_meeting_returns_prep_context(self) -> None:
        from src.tools.calendar import handle_meeting_prep

        client = MagicMock()
        event = _make_event(
            event_id="evt_standup",
            summary="Daily Standup",
            attendees=["alice@example.com"],
            start_offset_hours=1.0,
        )
        cal_ctx = _make_calendar_ctx(events=[event])
        client.search_messages.return_value = {"messages": [{"id": "m1", "threadId": "t1"}]}

        result = handle_meeting_prep({"hoursAhead": 4}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "Daily Standup" in text
        assert "Meeting Prep" in text

    def test_no_upcoming_in_window_returns_no_meetings_text(self) -> None:
        from src.tools.calendar import handle_meeting_prep

        client = MagicMock()
        event = _make_event(
            event_id="evt_far",
            summary="Far Future Meeting",
            start_offset_hours=10.0,
        )
        cal_ctx = _make_calendar_ctx(events=[event])

        result = handle_meeting_prep({"hoursAhead": 2}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        assert "No meetings in the next" in result["content"][0]["text"]

    def test_event_id_filter_not_found_returns_error(self) -> None:
        from src.tools.calendar import handle_meeting_prep

        client = MagicMock()
        event = _make_event(event_id="evt_real")
        cal_ctx = _make_calendar_ctx(events=[event])

        result = handle_meeting_prep({"eventId": "evt_missing"}, _ctx(client, cal_ctx))

        assert result["isError"] is True
        assert "evt_missing" in result["content"][0]["text"]

    def test_all_day_events_excluded_from_upcoming(self) -> None:
        from src.tools.calendar import handle_meeting_prep

        client = MagicMock()
        event = _make_event(
            event_id="evt_allday",
            summary="All Day Event",
            start_offset_hours=1.0,
            is_all_day=True,
        )
        cal_ctx = _make_calendar_ctx(events=[event])

        result = handle_meeting_prep({"hoursAhead": 4}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        assert "No meetings in the next" in result["content"][0]["text"]

    def test_error_handling_returns_error_content(self) -> None:
        from src.tools.calendar import handle_meeting_prep

        client = MagicMock()
        cal_ctx = MagicMock()
        cal_ctx.get_today_events.side_effect = RuntimeError("calendar error")

        result = handle_meeting_prep({}, _ctx(client, cal_ctx))

        assert result["isError"] is True
        assert "RuntimeError" in result["content"][0]["text"]

    def test_no_calendar_ctx_returns_error(self) -> None:
        from src.tools.calendar import handle_meeting_prep

        client = MagicMock()
        result = handle_meeting_prep({}, _ctx(client, None))
        assert result["isError"] is True
        assert "Calendar not configured" in result["content"][0]["text"]


class TestHandleTodayBriefing:
    def test_includes_calendar_events_section(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}
        event = _make_event(summary="Morning Sync")
        cal_ctx = _make_calendar_ctx(events=[event])

        result = handle_today_briefing({"includeCalendar": True}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "Calendar" in text
        assert "Morning Sync" in text

    def test_no_unread_shows_no_unread_message(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}
        cal_ctx = _make_calendar_ctx(events=[])

        result = handle_today_briefing({}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "No unread messages" in text

    def test_include_calendar_false_skips_calendar_section(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}
        cal_ctx = _make_calendar_ctx(events=[_make_event(summary="Hidden Meeting")])

        result = handle_today_briefing({"includeCalendar": False}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "Hidden Meeting" not in text
        assert "Calendar" not in text

    def test_all_day_event_shown_with_all_day_label(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}
        event = _make_event(summary="Company Holiday", is_all_day=True)
        cal_ctx = _make_calendar_ctx(events=[event])

        result = handle_today_briefing({"includeCalendar": True}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "All day" in text
        assert "Company Holiday" in text

    def test_no_calendar_events_shows_no_events_message(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}
        cal_ctx = _make_calendar_ctx(events=[])

        result = handle_today_briefing({"includeCalendar": True}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        assert "No events today" in result["content"][0]["text"]

    def test_scores_unread_messages_with_calendar_context(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": [{"id": "msg_001", "threadId": "t1"}]}
        client.read_message.return_value = {
            "id": "msg_001",
            "threadId": "t1",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "me@gmail.com"},
                    {"name": "Subject", "value": "Hello"},
                    {"name": "Date", "value": "Thu, 02 Apr 2026 10:00:00 -0400"},
                ],
                "parts": [{"mimeType": "text/plain", "body": {"data": ""}}],
            },
        }
        cal_ctx = _make_calendar_ctx(events=[])

        result = handle_today_briefing({}, _ctx(client, cal_ctx))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        assert "msg_001" in text

    def test_error_handling_returns_error_content(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.side_effect = RuntimeError("API failure")
        cal_ctx = _make_calendar_ctx()

        result = handle_today_briefing({}, _ctx(client, cal_ctx))

        assert result["isError"] is True
        assert "RuntimeError" in result["content"][0]["text"]

    def test_no_calendar_ctx_returns_error(self) -> None:
        from src.tools.calendar import handle_today_briefing

        client = MagicMock()
        client.email_address = "me@gmail.com"
        result = handle_today_briefing({}, _ctx(client, None))
        assert result["isError"] is True
        assert "Calendar not configured" in result["content"][0]["text"]
