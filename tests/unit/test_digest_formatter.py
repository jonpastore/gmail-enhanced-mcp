"""Unit tests for digest formatters."""

from __future__ import annotations

from src.digest.engine import DigestActionable, DigestItem, DigestResult, DigestSummary
from src.digest.formatter import format_digest_html, format_digest_text


def _make_result(
    top_items: list[DigestItem] | None = None,
    needs_reply: list[dict] | None = None,
    deadlines: list[dict] | None = None,
    calendar_conflicts: list[dict] | None = None,
) -> DigestResult:
    return DigestResult(
        account="test@gmail.com",
        period="daily",
        generated_at="2026-04-02T08:00:00-04:00",
        summary=DigestSummary(
            total_unread=47,
            by_category={"critical": 2, "high": 5, "normal": 28, "low": 8, "junk": 4},
            top_items=top_items
            if top_items is not None
            else [
                DigestItem(
                    message_id="m1",
                    from_addr="irs@irs.gov",
                    subject="IRS Notice",
                    category="critical",
                    score=0.95,
                    link="https://mail.google.com/mail/u/0/#inbox/m1",
                ),
                DigestItem(
                    message_id="m2",
                    from_addr="boss@company.com",
                    subject="Q2 Review",
                    category="high",
                    score=0.65,
                    link="https://mail.google.com/mail/u/0/#inbox/m2",
                ),
            ],
        ),
        actionable=DigestActionable(
            needs_reply=needs_reply
            if needs_reply is not None
            else [
                {
                    "message_id": "m3",
                    "from": "alice@example.com",
                    "subject": "Can you review?",
                    "reason": "Direct question",
                    "link": "https://mail.google.com/mail/u/0/#inbox/m3",
                }
            ],
            deadlines=deadlines
            if deadlines is not None
            else [
                {
                    "message_id": "m4",
                    "subject": "Report due April 5",
                    "deadline_date": "2026-04-05",
                    "context": "deadline",
                    "link": "https://mail.google.com/mail/u/0/#inbox/m4",
                }
            ],
            calendar_conflicts=calendar_conflicts if calendar_conflicts is not None else [],
        ),
    )


class TestFormatDigestHtml:
    def test_returns_valid_html(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert html.strip().startswith("<div")
        assert "</div>" in html

    def test_includes_account_name(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert "test@gmail.com" in html

    def test_includes_deep_links_as_href(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert 'href="https://mail.google.com/mail/u/0/#inbox/m1"' in html
        assert 'href="https://mail.google.com/mail/u/0/#inbox/m2"' in html

    def test_includes_category_badges(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert "CRITICAL" in html
        assert "HIGH" in html

    def test_handles_empty_top_items(self) -> None:
        result = _make_result(top_items=[])
        html = format_digest_html(result)

        assert "All clear" in html

    def test_includes_needs_reply_section(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert "Can you review?" in html
        assert "alice@example.com" in html
        assert "Direct question" in html

    def test_needs_reply_shows_zero_when_empty(self) -> None:
        result = _make_result(needs_reply=[])
        html = format_digest_html(result)

        assert "Needs Your Reply (0)" in html
        assert "No messages need your reply" in html

    def test_omits_calendar_section_when_no_events(self) -> None:
        result = _make_result(calendar_conflicts=[])
        html = format_digest_html(result)

        assert "Calendar Today" not in html

    def test_includes_calendar_section_when_events_present(self) -> None:
        result = _make_result(calendar_conflicts=[{"summary": "Team standup", "start": "09:00"}])
        html = format_digest_html(result)

        assert "Calendar Today" in html
        assert "Team standup" in html
        assert "09:00" in html

    def test_includes_deadline_section(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert "Report due April 5" in html
        assert "2026-04-05" in html

    def test_includes_generated_date(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert "2026-04-02" in html

    def test_includes_unread_count(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert "47 unread" in html

    def test_category_summary_line_present(self) -> None:
        result = _make_result()
        html = format_digest_html(result)

        assert "Critical: 2" in html
        assert "High: 5" in html


class TestFormatDigestText:
    def test_returns_plain_text(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "<" not in text
        assert ">" not in text

    def test_includes_account_name(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "test@gmail.com" in text

    def test_includes_urls_inline(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "https://mail.google.com/mail/u/0/#inbox/m1" in text

    def test_includes_all_sections(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "=== Summary ===" in text
        assert "=== Top Items ===" in text
        assert "=== Needs Your Reply" in text
        assert "=== Follow-up Deadlines ===" in text
        assert "=== Overdue Follow-ups ===" in text

    def test_includes_category_counts(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "Critical: 2" in text
        assert "High: 5" in text

    def test_includes_needs_reply_details(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "Can you review?" in text
        assert "alice@example.com" in text

    def test_includes_deadline_info(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "Report due April 5" in text
        assert "2026-04-05" in text

    def test_empty_top_items_message(self) -> None:
        result = _make_result(top_items=[])
        text = format_digest_text(result)

        assert "All clear" in text

    def test_calendar_section_omitted_when_empty(self) -> None:
        result = _make_result(calendar_conflicts=[])
        text = format_digest_text(result)

        assert "=== Calendar Today ===" not in text

    def test_calendar_section_present_when_events_exist(self) -> None:
        result = _make_result(calendar_conflicts=[{"summary": "Team standup", "start": "09:00"}])
        text = format_digest_text(result)

        assert "=== Calendar Today ===" in text
        assert "Team standup" in text

    def test_footer_present(self) -> None:
        result = _make_result()
        text = format_digest_text(result)

        assert "Gmail Enhanced MCP" in text
