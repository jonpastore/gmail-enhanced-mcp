"""Tests for DeadlineExtractor."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.triage.tracker import DeadlineExtractor


@pytest.fixture()
def extractor() -> DeadlineExtractor:
    return DeadlineExtractor()


class TestByPattern:
    """Test 'by March 15' / 'by March 15th' pattern."""

    def test_by_month_day(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract("Please reply by March 15", "", reference=ref)
        assert result is not None
        assert result.month == 3
        assert result.day == 15

    def test_by_month_day_with_ordinal(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract("Submit by March 15th", "", reference=ref)
        assert result is not None
        assert result.month == 3
        assert result.day == 15


class TestDeadlineColonPattern:
    """Test 'deadline: 2026-04-01' / 'deadline 04/01/2026' pattern."""

    def test_deadline_iso_date(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract("deadline: 2026-04-01", "", reference=ref)
        assert result is not None
        assert result.month == 4
        assert result.day == 1
        assert result.year == 2026

    def test_deadline_us_date(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract("deadline 04/01/2026", "", reference=ref)
        assert result is not None
        assert result.month == 4
        assert result.day == 1
        assert result.year == 2026


class TestDueByPattern:
    """Test 'due by end of day Friday' pattern."""

    def test_due_by_end_of_day_friday(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 30, tzinfo=UTC)  # Monday
        result = extractor.extract("due by end of day Friday", "", reference=ref)
        assert result is not None
        assert result.weekday() == 4  # Friday


class TestRespondByPattern:
    """Test 'respond by April 5th' pattern."""

    def test_respond_by_month_day(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract("respond by April 5th", "", reference=ref)
        assert result is not None
        assert result.month == 4
        assert result.day == 5


class TestExpiresOnPattern:
    """Test 'expires on 04/15/2026' pattern."""

    def test_expires_on_us_date(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract("expires on 04/15/2026", "", reference=ref)
        assert result is not None
        assert result.month == 4
        assert result.day == 15
        assert result.year == 2026


class TestEdgeCases:
    def test_no_deadline_returns_none(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract("Hello, how are you?", "", reference=ref)
        assert result is None

    def test_multiple_deadlines_returns_earliest(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        result = extractor.extract(
            "deadline: 2026-04-15",
            "respond by April 5th please",
            reference=ref,
        )
        assert result is not None
        assert result.month == 4
        assert result.day == 5

    def test_past_dates_still_extracted(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 5, 1, tzinfo=UTC)
        result = extractor.extract("by March 15", "", reference=ref)
        assert result is not None
        assert result.month == 3

    def test_body_snippet_limited_to_500_chars(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        long_body = "x" * 499 + " deadline: 2026-04-01"
        result = extractor.extract("no deadline here", long_body, reference=ref)
        assert result is None

    def test_deadline_in_body_within_limit(self, extractor: DeadlineExtractor) -> None:
        ref = datetime(2026, 3, 1, tzinfo=UTC)
        body = "Please note deadline: 2026-04-01 for submission"
        result = extractor.extract("no deadline here", body, reference=ref)
        assert result is not None
        assert result.month == 4
