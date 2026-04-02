from __future__ import annotations

import re
from datetime import date, time
from typing import ClassVar

from dateutil import parser as dateutil_parser
from dateutil.relativedelta import FR, MO, SA, SU, TH, TU, WE, relativedelta
from pydantic import BaseModel


class DateMention(BaseModel):
    """A date/time reference extracted from email text."""

    raw_text: str
    resolved_date: date
    resolved_time: time | None = None
    confidence: float


_WEEKDAY_MAP = {
    "monday": MO(1),
    "tuesday": TU(1),
    "wednesday": WE(1),
    "thursday": TH(1),
    "friday": FR(1),
    "saturday": SA(1),
    "sunday": SU(1),
}

_MONTH_NAMES = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

_PATTERNS: ClassVar[list[tuple[str, str, float]]] = [
    ("iso_dash", r"\b(\d{4}-\d{2}-\d{2})\b", 0.95),
    ("iso_slash", r"\b(\d{2}/\d{2}/\d{4})\b", 0.95),
    (
        "month_day",
        rf"\b({_MONTH_NAMES})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
        0.90,
    ),
    ("tomorrow", r"\b(tomorrow)\b", 0.85),
    (
        "next_weekday",
        r"\bnext\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        0.85,
    ),
]

_TIME_PATTERN = re.compile(r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.IGNORECASE)


def _resolve_time(raw: str) -> time | None:
    try:
        parsed = dateutil_parser.parse(raw)
        return parsed.time()
    except Exception:
        return None


class DateParser:
    """Extract date/time references from email text.

    V1 scope supports ISO dates, month-day expressions, relative terms
    (tomorrow, next <weekday>), and optional time components ("at 2pm").
    """

    def __init__(self, user_timezone: str = "America/New_York") -> None:
        """Initialize with a user timezone for relative-date resolution.

        Args:
            user_timezone: IANA timezone string used for relative dates.
        """
        self._user_timezone = user_timezone
        self._compiled: list[tuple[str, re.Pattern[str], float]] = [
            (name, re.compile(pat, re.IGNORECASE), conf) for name, pat, conf in _PATTERNS
        ]

    def extract_dates(self, text: str, reference_date: date | None = None) -> list[DateMention]:
        """Extract date/time mentions from text.

        V1 supports:
        1. ISO dates: "2026-04-05", "04/05/2026"
        2. Month day: "April 5", "April 5th", "Apr 5"
        3. Relative: "tomorrow", "next Monday" through "next Sunday"
        4. Combined: "April 5 at 2pm", "tomorrow at 3:30"

        Does NOT support: "end of Q2", "the 5th", "next week"

        Args:
            text: The email body or subject to scan.
            reference_date: Override today's date for relative resolution.

        Returns:
            List of DateMention instances, deduplicated by resolved_date.
        """
        ref = reference_date or date.today()
        results: list[DateMention] = []
        seen_dates: set[date] = set()

        for name, pattern, confidence in self._compiled:
            for match in pattern.finditer(text):
                resolved = self._resolve_match(name, match, ref)
                if resolved is None or resolved in seen_dates:
                    continue
                seen_dates.add(resolved)

                raw = match.group(0)
                resolved_time = self._extract_time_near(text, match.end())

                results.append(
                    DateMention(
                        raw_text=raw,
                        resolved_date=resolved,
                        resolved_time=resolved_time,
                        confidence=confidence,
                    )
                )

        return results

    def _resolve_match(self, name: str, match: re.Match[str], ref: date) -> date | None:
        if name == "iso_dash":
            try:
                return dateutil_parser.parse(match.group(1)).date()
            except Exception:
                return None

        if name == "iso_slash":
            try:
                return dateutil_parser.parse(match.group(1)).date()
            except Exception:
                return None

        if name == "month_day":
            month_str = match.group(1)
            day_str = match.group(2)
            try:
                parsed = dateutil_parser.parse(f"{month_str} {day_str} {ref.year}")
                candidate = parsed.date()
                if candidate < ref:
                    candidate = candidate.replace(year=ref.year + 1)
                return candidate
            except Exception:
                return None

        if name == "tomorrow":
            from datetime import timedelta

            return ref + timedelta(days=1)

        if name == "next_weekday":
            weekday_name = match.group(1).lower()
            delta = _WEEKDAY_MAP.get(weekday_name)
            if delta is None:
                return None
            return (ref + relativedelta(weekday=delta)).replace()

        return None

    def _extract_time_near(self, text: str, pos: int) -> time | None:
        window = text[pos : pos + 30]
        m = _TIME_PATTERN.match(window)
        if m:
            return _resolve_time(m.group(1))
        return None
