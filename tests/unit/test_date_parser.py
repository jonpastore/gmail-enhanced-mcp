from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.calendar.date_parser import DateParser


@pytest.fixture
def parser() -> DateParser:
    return DateParser(user_timezone="America/New_York")


REF_DATE = date(2026, 4, 1)


class TestISODates:
    def test_iso_dash_date_extracted(self, parser: DateParser) -> None:
        results = parser.extract_dates("Meeting on 2026-04-05", reference_date=REF_DATE)

        assert len(results) == 1
        assert results[0].resolved_date == date(2026, 4, 5)

    def test_iso_slash_date_extracted(self, parser: DateParser) -> None:
        results = parser.extract_dates("Due by 04/05/2026", reference_date=REF_DATE)

        assert len(results) == 1
        assert results[0].resolved_date == date(2026, 4, 5)

    def test_iso_dash_has_high_confidence(self, parser: DateParser) -> None:
        results = parser.extract_dates("2026-04-05", reference_date=REF_DATE)

        assert results[0].confidence == 0.95

    def test_iso_slash_has_high_confidence(self, parser: DateParser) -> None:
        results = parser.extract_dates("04/05/2026", reference_date=REF_DATE)

        assert results[0].confidence == 0.95


class TestMonthDayExpressions:
    def test_month_day_full_name_extracted(self, parser: DateParser) -> None:
        results = parser.extract_dates("April 5", reference_date=REF_DATE)

        assert len(results) == 1
        assert results[0].resolved_date == date(2026, 4, 5)

    def test_month_day_with_ordinal_suffix_extracted(self, parser: DateParser) -> None:
        results = parser.extract_dates("April 5th", reference_date=REF_DATE)

        assert len(results) == 1
        assert results[0].resolved_date == date(2026, 4, 5)

    def test_abbreviated_month_extracted(self, parser: DateParser) -> None:
        results = parser.extract_dates("Apr 5", reference_date=REF_DATE)

        assert len(results) == 1
        assert results[0].resolved_date == date(2026, 4, 5)

    def test_past_month_day_rolls_to_next_year(self, parser: DateParser) -> None:
        past_ref = date(2026, 4, 10)
        results = parser.extract_dates("April 5", reference_date=past_ref)

        assert results[0].resolved_date == date(2027, 4, 5)

    def test_month_day_same_day_does_not_roll(self, parser: DateParser) -> None:
        same_ref = date(2026, 4, 5)
        results = parser.extract_dates("April 5", reference_date=same_ref)

        assert results[0].resolved_date == date(2026, 4, 5)


class TestRelativeDates:
    def test_tomorrow_resolves_to_next_day(self, parser: DateParser) -> None:
        results = parser.extract_dates("Meet tomorrow", reference_date=REF_DATE)

        assert len(results) == 1
        assert results[0].resolved_date == REF_DATE + timedelta(days=1)

    def test_next_monday_resolves_to_correct_date(self, parser: DateParser) -> None:
        results = parser.extract_dates("Let's meet next Monday", reference_date=REF_DATE)

        assert len(results) == 1
        resolved = results[0].resolved_date
        assert resolved.weekday() == 0
        assert resolved > REF_DATE

    def test_next_friday_resolves_to_correct_date(self, parser: DateParser) -> None:
        results = parser.extract_dates("Deadline next Friday", reference_date=REF_DATE)

        resolved = results[0].resolved_date
        assert resolved.weekday() == 4
        assert resolved > REF_DATE

    def test_tomorrow_has_expected_confidence(self, parser: DateParser) -> None:
        results = parser.extract_dates("tomorrow", reference_date=REF_DATE)

        assert results[0].confidence == 0.85


class TestTimeExtraction:
    def test_iso_date_without_time_has_none_time(self, parser: DateParser) -> None:
        results = parser.extract_dates("2026-04-05", reference_date=REF_DATE)

        assert results[0].resolved_time is None

    def test_month_day_without_adjacent_time_has_none_time(self, parser: DateParser) -> None:
        results = parser.extract_dates("April 5", reference_date=REF_DATE)

        assert results[0].resolved_time is None

    def test_tomorrow_without_adjacent_time_has_none_time(self, parser: DateParser) -> None:
        results = parser.extract_dates("tomorrow", reference_date=REF_DATE)

        assert results[0].resolved_time is None


class TestEdgeCases:
    def test_no_dates_returns_empty_list(self, parser: DateParser) -> None:
        results = parser.extract_dates("No dates here", reference_date=REF_DATE)

        assert results == []

    def test_duplicate_dates_deduplicated(self, parser: DateParser) -> None:
        results = parser.extract_dates("April 5 and April 5th", reference_date=REF_DATE)

        resolved_dates = [r.resolved_date for r in results]
        assert resolved_dates.count(date(2026, 4, 5)) == 1

    def test_raw_text_preserved_in_result(self, parser: DateParser) -> None:
        results = parser.extract_dates("2026-04-05", reference_date=REF_DATE)

        assert results[0].raw_text == "2026-04-05"

    def test_multiple_distinct_dates_all_returned(self, parser: DateParser) -> None:
        results = parser.extract_dates(
            "Call on 2026-04-05 and follow-up on 2026-04-10", reference_date=REF_DATE
        )

        resolved = {r.resolved_date for r in results}
        assert date(2026, 4, 5) in resolved
        assert date(2026, 4, 10) in resolved
