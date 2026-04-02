"""Follow-up tracker and deadline extraction for sent messages."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from .cache import TriageCache
from .models import FollowUp, FollowUpStatus

_MONTH_MAP: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_DAY_MAP: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_BODY_SNIPPET_LIMIT = 500


class DeadlineExtractor:
    """Extract deadline dates from email subject and body snippet using regex patterns."""

    PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        (
            "by_month_day",
            re.compile(
                r"(?:by|before)\s+"
                r"(january|february|march|april|may|june|july|august|"
                r"september|october|november|december|"
                r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
                r"\s+(\d{1,2})(?:st|nd|rd|th)?",
                re.IGNORECASE,
            ),
        ),
        (
            "respond_by_month_day",
            re.compile(
                r"respond\s+by\s+"
                r"(january|february|march|april|may|june|july|august|"
                r"september|october|november|december|"
                r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
                r"\s+(\d{1,2})(?:st|nd|rd|th)?",
                re.IGNORECASE,
            ),
        ),
        (
            "deadline_iso",
            re.compile(
                r"deadline[:\s]+(\d{4})-(\d{2})-(\d{2})",
                re.IGNORECASE,
            ),
        ),
        (
            "deadline_us",
            re.compile(
                r"deadline[:\s]+(\d{2})/(\d{2})/(\d{4})",
                re.IGNORECASE,
            ),
        ),
        (
            "due_by_weekday",
            re.compile(
                r"due\s+by\s+(?:end\s+of\s+day\s+)?"
                r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                re.IGNORECASE,
            ),
        ),
        (
            "expires_on",
            re.compile(
                r"expires?\s+on\s+(\d{2})/(\d{2})/(\d{4})",
                re.IGNORECASE,
            ),
        ),
    ]

    def extract(
        self,
        subject: str,
        body_snippet: str,
        *,
        reference: datetime | None = None,
    ) -> datetime | None:
        """Return earliest deadline found, or None.

        Args:
            subject: Email subject line.
            body_snippet: First 500 chars of the email body (privacy).
            reference: Reference date for relative dates. Defaults to now.

        Returns:
            Earliest deadline datetime or None if no deadline found.
        """
        ref = reference or datetime.now(tz=UTC)
        truncated_body = body_snippet[:_BODY_SNIPPET_LIMIT]
        text = f"{subject} {truncated_body}"
        dates: list[datetime] = []
        for pattern_name, pattern in self.PATTERNS:
            for match in pattern.finditer(text):
                parsed = self._parse_match(pattern_name, match, ref)
                if parsed is not None:
                    dates.append(parsed)
        if not dates:
            return None
        return min(dates)

    def _parse_match(
        self, pattern_name: str, match: re.Match[str], ref: datetime
    ) -> datetime | None:
        """Parse a regex match into a datetime based on pattern type."""
        if pattern_name in ("by_month_day", "respond_by_month_day"):
            return self._parse_month_day(match.group(1), match.group(2), ref)
        if pattern_name == "deadline_iso":
            return self._parse_absolute_date(
                int(match.group(1)), int(match.group(2)), int(match.group(3)), ref
            )
        if pattern_name == "deadline_us":
            return self._parse_absolute_date(
                int(match.group(3)), int(match.group(1)), int(match.group(2)), ref
            )
        if pattern_name == "due_by_weekday":
            return self._parse_relative_weekday(match.group(1), ref)
        if pattern_name == "expires_on":
            return self._parse_absolute_date(
                int(match.group(3)), int(match.group(1)), int(match.group(2)), ref
            )
        return None

    def _parse_month_day(self, month_str: str, day_str: str, ref: datetime) -> datetime | None:
        """Parse 'March 15' into a datetime."""
        month = _MONTH_MAP.get(month_str.lower())
        if month is None:
            return None
        day = int(day_str)
        year = ref.year
        return datetime(year, month, day, tzinfo=UTC)

    def _parse_absolute_date(
        self, year: int, month: int, day: int, ref: datetime
    ) -> datetime | None:
        """Parse an absolute year-month-day into a datetime."""
        try:
            return datetime(year, month, day, tzinfo=UTC)
        except ValueError:
            return None

    def _parse_relative_weekday(self, day_name: str, ref: datetime) -> datetime | None:
        """Parse a weekday name into the next occurrence from reference."""
        target = _DAY_MAP.get(day_name.lower())
        if target is None:
            return None
        current = ref.weekday()
        days_ahead = (target - current) % 7
        if days_ahead == 0:
            days_ahead = 7
        return datetime(ref.year, ref.month, ref.day, tzinfo=UTC) + timedelta(days=days_ahead)


def _get_header(msg: dict[str, Any], name: str) -> str:
    """Extract a header value from a Gmail message dict."""
    headers: list[dict[str, str]] = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


class FollowUpTracker:
    """Track sent messages awaiting replies."""

    def __init__(self, cache: TriageCache) -> None:
        self._cache = cache
        self._extractor = DeadlineExtractor()

    def track(
        self,
        msg: dict[str, Any],
        account: str,
        expected_days: int = 3,
    ) -> FollowUp:
        """Start tracking a sent message. EXPLICIT only -- user must call this.

        Stores subject_hash (not plaintext) in cache.

        Args:
            msg: Gmail message dict with payload.headers.
            account: Account email address.
            expected_days: Days to wait before marking overdue.

        Returns:
            The created FollowUp.
        """
        subject = _get_header(msg, "Subject")
        date_str = _get_header(msg, "Date")
        body_snippet = msg.get("payload", {}).get("body", {}).get("data", "")

        sent_date = self._parse_date(date_str)
        subject_hash = TriageCache.hash_address(subject)
        deadline = self._extractor.extract(
            subject, body_snippet[:_BODY_SNIPPET_LIMIT], reference=sent_date
        )
        account_hash = TriageCache.hash_address(account)

        follow_up = FollowUp(
            message_id=msg["id"],
            thread_id=msg["threadId"],
            subject_hash=subject_hash,
            sent_date=sent_date,
            expected_reply_days=expected_days,
            deadline=deadline,
            status=FollowUpStatus.WAITING,
        )

        self._cache.add_follow_up(follow_up, account_hash=account_hash)
        return follow_up

    def check_replies(self, client: Any, account: str) -> list[FollowUp]:
        """Check waiting follow-ups for replies via client.read_thread().

        Updates status to REPLIED if thread has new messages from other senders.

        Args:
            client: Gmail client with read_thread(thread_id) method.
            account: Account email address.

        Returns:
            List of follow-ups that received replies.
        """
        account_hash = TriageCache.hash_address(account)
        waiting = self._cache.get_follow_ups(account_hash, status=FollowUpStatus.WAITING)
        replied: list[FollowUp] = []

        for fu in waiting:
            thread = client.read_thread(fu.thread_id)
            messages: list[dict[str, Any]] = thread.get("messages", [])
            has_reply = self._thread_has_reply(messages, account, fu.sent_date)
            if has_reply:
                row_id = self._get_follow_up_row_id(fu)
                self._cache.update_follow_up_status(row_id, FollowUpStatus.REPLIED)
                replied.append(fu.model_copy(update={"status": FollowUpStatus.REPLIED}))

        return replied

    def get_overdue(self, account: str) -> list[FollowUp]:
        """Return follow-ups past expected_reply_days with no reply.

        Args:
            account: Account email address.

        Returns:
            List of overdue follow-ups.
        """
        account_hash = TriageCache.hash_address(account)
        waiting = self._cache.get_follow_ups(account_hash, status=FollowUpStatus.WAITING)
        now = datetime.now(tz=UTC)
        return [fu for fu in waiting if fu.sent_date + timedelta(days=fu.expected_reply_days) < now]

    def get_approaching_deadline(self, account: str, within_days: int = 2) -> list[FollowUp]:
        """Return follow-ups with deadlines within N days.

        Args:
            account: Account email address.
            within_days: Number of days to look ahead.

        Returns:
            List of follow-ups with approaching deadlines.
        """
        account_hash = TriageCache.hash_address(account)
        waiting = self._cache.get_follow_ups(account_hash, status=FollowUpStatus.WAITING)
        now = datetime.now(tz=UTC)
        cutoff = now + timedelta(days=within_days)
        return [fu for fu in waiting if fu.deadline is not None and now <= fu.deadline <= cutoff]

    def dismiss(self, follow_up_id: int) -> None:
        """Mark a follow-up as dismissed.

        Args:
            follow_up_id: Database row ID of the follow-up.
        """
        self._cache.update_follow_up_status(follow_up_id, FollowUpStatus.DISMISSED)

    def list_active(self, account: str) -> list[FollowUp]:
        """All waiting follow-ups for an account.

        Args:
            account: Account email address.

        Returns:
            List of active (waiting) follow-ups.
        """
        account_hash = TriageCache.hash_address(account)
        return self._cache.get_follow_ups(account_hash, status=FollowUpStatus.WAITING)

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse an RFC 2822 date string into a UTC datetime."""
        if not date_str:
            return datetime.now(tz=UTC)
        try:
            return parsedate_to_datetime(date_str).astimezone(UTC)
        except (ValueError, TypeError):
            return datetime.now(tz=UTC)

    @staticmethod
    def _thread_has_reply(messages: list[dict[str, Any]], account: str, since: datetime) -> bool:
        """Check if any message in the thread is from someone other than account."""
        account_lower = account.lower()
        for msg in messages:
            from_addr = _get_header(msg, "From").lower()
            if account_lower not in from_addr:
                date_str = _get_header(msg, "Date")
                if date_str:
                    try:
                        msg_date = parsedate_to_datetime(date_str).astimezone(UTC)
                        if msg_date > since:
                            return True
                    except (ValueError, TypeError):
                        continue
        return False

    def _get_follow_up_row_id(self, fu: FollowUp) -> int:
        """Look up the database row ID for a follow-up by message_id."""
        rows = self._cache._execute_read(
            "SELECT id FROM follow_ups WHERE message_id = ?",
            (fu.message_id,),
        )
        if rows:
            return int(rows[0]["id"])
        return 0
