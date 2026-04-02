from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    """A single calendar event."""

    event_id: str
    summary: str
    start: datetime
    end: datetime
    attendee_emails: list[str] = []
    location: str | None = None
    is_all_day: bool = False
    timezone: str = "America/New_York"


class ConflictResult(BaseModel):
    """Result of checking a date mention against the calendar."""

    email_message_id: str
    date_mention: Any
    conflicting_events: list[CalendarEvent]
    severity: str


class MeetingPrepContext(BaseModel):
    """Context gathered for meeting preparation."""

    event: CalendarEvent
    related_threads: list[dict[str, Any]] = []
    attendee_match_count: int = 0


@runtime_checkable
class CalendarContext(Protocol):
    """Protocol for calendar context lookups."""

    def get_today_events(self) -> list[CalendarEvent]: ...

    def get_events_for_date(self, target: date) -> list[CalendarEvent]: ...

    def is_meeting_attendee(self, email: str, hours_ahead: int = 24) -> bool: ...

    def prime_for_date(self, target: date) -> None: ...


class GoogleCalendarContext:
    """CalendarContext implementation backed by a CalendarProvider."""

    def __init__(self, client: Any) -> None:
        """Initialize with a CalendarProvider instance.

        Args:
            client: Any object implementing the CalendarProvider protocol.
        """
        self._client = client
        self._events_cache: dict[date, list[CalendarEvent]] = {}
        self._attendee_set: set[str] = set()

    def _resolve_timezone(self) -> str:
        if hasattr(self._client, "_user_timezone"):
            return str(self._client._user_timezone)
        return "America/New_York"

    def prime_for_date(self, target: date) -> None:
        """Fetch and cache events for the given date if not already cached.

        Args:
            target: The date to fetch events for.
        """
        if target in self._events_cache:
            return
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(self._resolve_timezone())
        start = datetime.combine(target, time.min, tzinfo=tz)
        end = datetime.combine(target, time.max, tzinfo=tz)
        events = self._client.list_events(time_min=start, time_max=end)
        self._events_cache[target] = events
        for ev in events:
            self._attendee_set.update(e.lower() for e in ev.attendee_emails)

    def get_today_events(self) -> list[CalendarEvent]:
        """Return all events for today.

        Returns:
            List of CalendarEvent instances for today.
        """
        today = date.today()
        self.prime_for_date(today)
        return self._events_cache[today]

    def get_events_for_date(self, target: date) -> list[CalendarEvent]:
        """Return all events for the given date.

        Args:
            target: The date to retrieve events for.

        Returns:
            List of CalendarEvent instances for that date.
        """
        self.prime_for_date(target)
        return self._events_cache[target]

    def is_meeting_attendee(self, email: str, hours_ahead: int = 24) -> bool:
        """Check if the given email appears in any upcoming meeting attendee list.

        Uses the local attendee set. If not yet primed, primes today and
        tomorrow when hours_ahead <= 24, otherwise primes today only.

        Args:
            email: Email address to look up.
            hours_ahead: How far ahead to look when auto-priming.

        Returns:
            True if the email is found among meeting attendees.
        """
        if not self._events_cache:
            today = date.today()
            self.prime_for_date(today)
            if hours_ahead > 24:
                from datetime import timedelta

                self.prime_for_date(today + timedelta(days=1))
        return email.lower() in self._attendee_set
