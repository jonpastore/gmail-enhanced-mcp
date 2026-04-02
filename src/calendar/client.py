from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from dateutil import parser as dateutil_parser
from googleapiclient.discovery import build
from loguru import logger

from ..auth import TokenManager
from .context import CalendarEvent


@runtime_checkable
class CalendarProvider(Protocol):
    """Protocol for calendar read access."""

    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
        calendar_id: str = "primary",
        max_results: int = 50,
    ) -> list[CalendarEvent]: ...

    def get_event(self, event_id: str, calendar_id: str = "primary") -> CalendarEvent: ...

    def check_freebusy(
        self,
        time_min: datetime,
        time_max: datetime,
        calendar_ids: list[str] | None = None,
    ) -> dict[str, list[tuple[datetime, datetime]]]: ...


def _parse_event(raw: dict[str, Any], user_timezone: str) -> CalendarEvent:
    """Parse a raw Google Calendar API event dict into a CalendarEvent.

    Args:
        raw: The event dict returned by the Calendar API.
        user_timezone: Default timezone for naive datetime fallback.

    Returns:
        A CalendarEvent model instance.
    """
    start_raw = raw.get("start", {})
    end_raw = raw.get("end", {})

    is_all_day = "date" in start_raw and "dateTime" not in start_raw

    if is_all_day:
        start_dt = dateutil_parser.isoparse(start_raw["date"])
        end_dt = dateutil_parser.isoparse(end_raw.get("date", start_raw["date"]))
    else:
        start_dt = dateutil_parser.isoparse(start_raw["dateTime"])
        end_dt = dateutil_parser.isoparse(end_raw["dateTime"])

    attendees = [a["email"] for a in raw.get("attendees", []) if "email" in a]

    return CalendarEvent(
        event_id=raw.get("id", ""),
        summary=raw.get("summary", "(No title)"),
        start=start_dt,
        end=end_dt,
        attendee_emails=attendees,
        location=raw.get("location"),
        is_all_day=is_all_day,
        timezone=start_raw.get("timeZone", user_timezone),
    )


class GoogleCalendarClient:
    """Read-only Google Calendar API wrapper implementing CalendarProvider."""

    def __init__(
        self, token_manager: TokenManager, user_timezone: str = "America/New_York"
    ) -> None:
        """Initialize and validate required OAuth scopes.

        Args:
            token_manager: Authenticated TokenManager instance.
            user_timezone: IANA timezone string for event queries.
        """
        token_manager.validate_scopes(["https://www.googleapis.com/auth/calendar.readonly"])
        self._token_mgr = token_manager
        self._user_timezone = user_timezone
        self._service: Any = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_ttl: float = 300.0

    def _get_service(self) -> Any:
        if self._service is None:
            creds = self._token_mgr.get_credentials()
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def _cache_get(self, key: str) -> Any | None:
        """Retrieve a cached value if not expired.

        Args:
            key: Cache key string.

        Returns:
            Cached value or None if missing/expired.
        """
        if key in self._cache:
            expires_at, value = self._cache[key]
            if time.monotonic() < expires_at:
                return value
            del self._cache[key]
        return None

    def _cache_set(self, key: str, value: Any) -> None:
        """Store a value in the cache with a TTL-based expiry.

        Args:
            key: Cache key string.
            value: Value to store.
        """
        self._cache[key] = (time.monotonic() + self._cache_ttl, value)

    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
        calendar_id: str = "primary",
        max_results: int = 50,
    ) -> list[CalendarEvent]:
        """List calendar events within a time window.

        Args:
            time_min: Start of the time range (inclusive).
            time_max: End of the time range (inclusive).
            calendar_id: Calendar to query (default: "primary").
            max_results: Maximum number of events to return.

        Returns:
            List of CalendarEvent instances sorted by start time.
        """
        cache_key = f"list:{calendar_id}:{time_min.isoformat()}:{time_max.isoformat()}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        svc = self._get_service()
        logger.debug(f"Fetching calendar events {time_min.isoformat()} – {time_max.isoformat()}")
        result = (
            svc.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                timeZone=self._user_timezone,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = [_parse_event(item, self._user_timezone) for item in result.get("items", [])]
        self._cache_set(cache_key, events)
        return events

    def get_event(self, event_id: str, calendar_id: str = "primary") -> CalendarEvent:
        """Fetch a single calendar event by ID.

        Args:
            event_id: The event's unique identifier.
            calendar_id: Calendar that owns the event (default: "primary").

        Returns:
            CalendarEvent for the requested event.
        """
        cache_key = f"event:{calendar_id}:{event_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        svc = self._get_service()
        logger.debug(f"Fetching calendar event {event_id}")
        raw = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        event = _parse_event(raw, self._user_timezone)
        self._cache_set(cache_key, event)
        return event

    def check_freebusy(
        self,
        time_min: datetime,
        time_max: datetime,
        calendar_ids: list[str] | None = None,
    ) -> dict[str, list[tuple[datetime, datetime]]]:
        """Query free/busy information for one or more calendars.

        Args:
            time_min: Start of the query window.
            time_max: End of the query window.
            calendar_ids: Calendars to query; defaults to ["primary"].

        Returns:
            Dict mapping calendar_id to a list of (start, end) busy periods.
        """
        ids = calendar_ids or ["primary"]
        cache_key = (
            f"freebusy:{','.join(sorted(ids))}" f":{time_min.isoformat()}:{time_max.isoformat()}"
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        svc = self._get_service()
        logger.debug(f"Checking freebusy for {ids}")
        body: dict[str, Any] = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "timeZone": self._user_timezone,
            "items": [{"id": cal_id} for cal_id in ids],
        }
        result = svc.freebusy().query(body=body).execute()

        calendars_raw = result.get("calendars", {})
        busy_map: dict[str, list[tuple[datetime, datetime]]] = {}
        for cal_id, cal_data in calendars_raw.items():
            periods: list[tuple[datetime, datetime]] = []
            for period in cal_data.get("busy", []):
                start = dateutil_parser.isoparse(period["start"])
                end = dateutil_parser.isoparse(period["end"])
                periods.append((start, end))
            busy_map[cal_id] = periods

        self._cache_set(cache_key, busy_map)
        return busy_map
