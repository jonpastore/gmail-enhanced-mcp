"""Tests for ImportanceScorer and JunkDetector."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest

from src.triage.cache import TriageCache
from src.triage.engine import ImportanceScorer, JunkDetector
from src.triage.models import (
    MessageCategory,
    PrioritySender,
    SenderTier,
)


@pytest.fixture()
def cache() -> TriageCache:
    c = TriageCache(db_path=Path(":memory:"))
    c.initialize()
    return c


@pytest.fixture()
def scorer(cache: TriageCache) -> ImportanceScorer:
    return ImportanceScorer(cache=cache)


@pytest.fixture()
def detector() -> JunkDetector:
    return JunkDetector()


def _make_msg(
    msg_id: str = "msg123",
    thread_id: str = "thread456",
    from_addr: str = "someone@example.com",
    to_addr: str = "jpastore79@gmail.com",
    subject: str = "Test Subject",
    date: str = "Mon, 31 Mar 2026 10:00:00 -0400",
    extra_headers: list[dict[str, str]] | None = None,
    label_ids: list[str] | None = None,
    has_parts: bool = False,
) -> dict[str, Any]:
    headers = [
        {"name": "From", "value": from_addr},
        {"name": "To", "value": to_addr},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": date},
    ]
    if extra_headers:
        headers.extend(extra_headers)

    payload: dict[str, Any] = {"headers": headers}
    if has_parts:
        payload["parts"] = [
            {"mimeType": "text/plain", "body": {"data": ""}},
            {
                "mimeType": "application/pdf",
                "filename": "doc.pdf",
                "body": {"attachmentId": "att1"},
            },
        ]
    else:
        payload["parts"] = [{"mimeType": "text/plain", "body": {"data": ""}}]

    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": label_ids or ["INBOX", "UNREAD"],
        "payload": payload,
    }


# -- Header extraction --


class TestExtractHeaders:
    def test_extracts_gmail_format_headers(self) -> None:
        msg = _make_msg(from_addr="a@b.com", subject="Hello")
        headers = ImportanceScorer.extract_headers(msg)
        assert headers["from"] == "a@b.com"
        assert headers["subject"] == "Hello"

    def test_lowercases_header_names(self) -> None:
        msg = _make_msg(
            extra_headers=[{"name": "List-Unsubscribe", "value": "<mailto:unsub@x.com>"}]
        )
        headers = ImportanceScorer.extract_headers(msg)
        assert "list-unsubscribe" in headers

    def test_empty_payload_returns_empty_dict(self) -> None:
        msg: dict[str, Any] = {"id": "x", "threadId": "t", "payload": {}}
        headers = ImportanceScorer.extract_headers(msg)
        assert headers == {}

    def test_missing_payload_returns_empty_dict(self) -> None:
        msg: dict[str, Any] = {"id": "x", "threadId": "t"}
        headers = ImportanceScorer.extract_headers(msg)
        assert headers == {}


# -- JunkDetector --


class TestJunkDetector:
    def test_clean_message_not_junk(self, detector: JunkDetector) -> None:
        msg = _make_msg()
        result = detector.analyze(msg)
        assert result.is_junk is False
        assert result.confidence == 0.0
        assert result.reasons == []

    def test_unsubscribe_header_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(
            extra_headers=[{"name": "List-Unsubscribe", "value": "<mailto:unsub@x.com>"}]
        )
        result = detector.analyze(msg)
        assert result.is_junk is True
        assert "has_unsubscribe_header" in result.reasons

    def test_precedence_bulk_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(extra_headers=[{"name": "Precedence", "value": "bulk"}])
        result = detector.analyze(msg)
        assert "precedence_bulk" in result.reasons

    def test_precedence_list_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(extra_headers=[{"name": "Precedence", "value": "list"}])
        result = detector.analyze(msg)
        assert "precedence_bulk" in result.reasons

    def test_noreply_sender_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(from_addr="noreply@example.com")
        result = detector.analyze(msg)
        assert "noreply_sender" in result.reasons

    def test_no_reply_sender_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(from_addr="no-reply@example.com")
        result = detector.analyze(msg)
        assert "noreply_sender" in result.reasons

    def test_newsletter_sender_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(from_addr="newsletter@example.com")
        result = detector.analyze(msg)
        assert "noreply_sender" in result.reasons

    def test_marketing_sender_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(from_addr="marketing@store.com")
        result = detector.analyze(msg)
        assert "noreply_sender" in result.reasons

    def test_mailing_list_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(extra_headers=[{"name": "List-Id", "value": "<list.example.com>"}])
        result = detector.analyze(msg)
        assert "mailing_list" in result.reasons

    def test_list_post_detected(self, detector: JunkDetector) -> None:
        msg = _make_msg(extra_headers=[{"name": "List-Post", "value": "<mailto:list@example.com>"}])
        result = detector.analyze(msg)
        assert "mailing_list" in result.reasons

    def test_confidence_one_signal(self, detector: JunkDetector) -> None:
        msg = _make_msg(extra_headers=[{"name": "List-Unsubscribe", "value": "<x>"}])
        result = detector.analyze(msg)
        assert result.confidence == pytest.approx(0.4)

    def test_confidence_two_signals(self, detector: JunkDetector) -> None:
        msg = _make_msg(
            from_addr="noreply@example.com",
            extra_headers=[{"name": "List-Unsubscribe", "value": "<x>"}],
        )
        result = detector.analyze(msg)
        assert result.confidence == pytest.approx(0.7)

    def test_confidence_three_signals(self, detector: JunkDetector) -> None:
        msg = _make_msg(
            from_addr="noreply@example.com",
            extra_headers=[
                {"name": "List-Unsubscribe", "value": "<x>"},
                {"name": "List-Id", "value": "<list.x.com>"},
            ],
        )
        result = detector.analyze(msg)
        assert result.confidence == pytest.approx(0.9)


# -- ImportanceScorer signals --


class TestScoringSignals:
    def test_priority_sender_critical_signal(
        self, scorer: ImportanceScorer, cache: TriageCache
    ) -> None:
        cache.add_priority_sender(
            PrioritySender(email_pattern="vip@irs.gov", tier=SenderTier.CRITICAL, label="IRS")
        )
        scorer._load_priority_senders()
        msg = _make_msg(from_addr="vip@irs.gov")
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "priority_sender_critical" in names

    def test_priority_sender_high_signal(
        self, scorer: ImportanceScorer, cache: TriageCache
    ) -> None:
        cache.add_priority_sender(
            PrioritySender(email_pattern="boss@work.com", tier=SenderTier.HIGH, label="Boss")
        )
        scorer._load_priority_senders()
        msg = _make_msg(from_addr="boss@work.com")
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "priority_sender_high" in names

    def test_direct_recipient_signal(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(to_addr="jpastore79@gmail.com")
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "direct_recipient" in names

    def test_cc_not_direct_recipient(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(to_addr="other@example.com")
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "direct_recipient" not in names

    def test_has_deadline_signal(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(subject="Action required by April 5")
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "has_deadline" in names

    def test_is_reply_to_me_signal(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(
            extra_headers=[{"name": "In-Reply-To", "value": "<abc@mail.gmail.com>"}],
            label_ids=["INBOX", "UNREAD"],
        )
        msg["payload"]["headers"].append({"name": "References", "value": "<abc@mail.gmail.com>"})
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "is_reply_to_me" in names

    def test_has_attachment_signal(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(has_parts=True)
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "has_attachment" in names

    def test_junk_detected_negative_signal(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(
            from_addr="noreply@spam.com",
            extra_headers=[{"name": "List-Unsubscribe", "value": "<x>"}],
        )
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "junk_detected" in names
        junk_signal = next(s for s in signals if s.name == "junk_detected")
        assert junk_signal.weight < 0

    def test_recent_message_signal(self, scorer: ImportanceScorer) -> None:
        from datetime import datetime

        now = datetime.now(tz=UTC)
        date_str = now.strftime("%a, %d %b %Y %H:%M:%S %z")
        msg = _make_msg(date=date_str)
        signals = scorer._extract_signals(msg, "jpastore79@gmail.com")
        names = [s.name for s in signals]
        assert "recent_24h" in names


# -- Score computation --


class TestScoreComputation:
    def test_score_clamped_to_zero_one(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(
            from_addr="noreply@spam.com",
            extra_headers=[
                {"name": "List-Unsubscribe", "value": "<x>"},
                {"name": "List-Id", "value": "<l>"},
                {"name": "Precedence", "value": "bulk"},
            ],
        )
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert 0.0 <= result.score <= 1.0

    def test_score_deterministic(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg()
        s1 = scorer.score_message(msg, "jpastore79@gmail.com")
        s2 = scorer.score_message(msg, "jpastore79@gmail.com")
        assert s1.score == s2.score
        assert s1.category == s2.category

    def test_batch_scoring_sorted_descending(
        self, scorer: ImportanceScorer, cache: TriageCache
    ) -> None:
        cache.add_priority_sender(
            PrioritySender(email_pattern="vip@irs.gov", tier=SenderTier.CRITICAL, label="IRS")
        )
        scorer._load_priority_senders()
        msgs = [
            _make_msg(
                msg_id="low",
                from_addr="noreply@spam.com",
                extra_headers=[{"name": "List-Unsubscribe", "value": "<x>"}],
            ),
            _make_msg(msg_id="high", from_addr="vip@irs.gov"),
        ]
        results = scorer.score_messages(msgs, "jpastore79@gmail.com")
        assert results[0].message_id == "high"
        assert results[0].score >= results[1].score

    def test_config_loading_from_json(self, cache: TriageCache, tmp_path: Path) -> None:
        config = {
            "weights": {"priority_sender_critical": 0.99, "direct_recipient": 0.01},
            "thresholds": {"critical": 0.90, "high": 0.50, "normal": 0.20, "low": 0.10},
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))
        s = ImportanceScorer(cache=cache, config_path=config_path)
        assert s._weights["priority_sender_critical"] == 0.99

    def test_config_fallback_to_defaults(self, cache: TriageCache) -> None:
        s = ImportanceScorer(cache=cache, config_path=Path("/nonexistent/config.json"))
        assert "priority_sender_critical" in s._weights


# -- Category thresholds --


class TestCategoryAssignment:
    def test_critical_threshold(self, scorer: ImportanceScorer, cache: TriageCache) -> None:
        cache.add_priority_sender(
            PrioritySender(email_pattern="*@irs.gov", tier=SenderTier.CRITICAL, label="IRS")
        )
        scorer._load_priority_senders()
        msg = _make_msg(from_addr="taxes@irs.gov", to_addr="jpastore79@gmail.com")
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert result.category == MessageCategory.CRITICAL

    def test_junk_category(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(
            from_addr="noreply@spam.com",
            to_addr="list@example.com",
            extra_headers=[
                {"name": "List-Unsubscribe", "value": "<x>"},
                {"name": "List-Id", "value": "<l>"},
                {"name": "Precedence", "value": "bulk"},
            ],
        )
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert result.category == MessageCategory.JUNK


# -- Calibration scenarios --


class TestCalibrationScenarios:
    def test_irs_direct_message_is_critical(
        self, scorer: ImportanceScorer, cache: TriageCache
    ) -> None:
        cache.add_priority_sender(
            PrioritySender(email_pattern="*@irs.gov", tier=SenderTier.CRITICAL, label="IRS")
        )
        scorer._load_priority_senders()
        msg = _make_msg(
            from_addr="taxes@irs.gov",
            to_addr="jpastore79@gmail.com",
            subject="Important Tax Notice",
        )
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert result.category == MessageCategory.CRITICAL

    def test_boss_reply_is_high(self, scorer: ImportanceScorer, cache: TriageCache) -> None:
        cache.add_priority_sender(
            PrioritySender(email_pattern="boss@work.com", tier=SenderTier.HIGH, label="Boss")
        )
        scorer._load_priority_senders()
        msg = _make_msg(
            from_addr="boss@work.com",
            to_addr="jpastore79@gmail.com",
            extra_headers=[{"name": "In-Reply-To", "value": "<prev@mail.gmail.com>"}],
        )
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert result.category in (MessageCategory.CRITICAL, MessageCategory.HIGH)

    def test_newsletter_with_unsubscribe_noreply_is_junk(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(
            from_addr="noreply@newsletter.com",
            to_addr="list-members@newsletter.com",
            extra_headers=[{"name": "List-Unsubscribe", "value": "<mailto:unsub@newsletter.com>"}],
        )
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert result.category == MessageCategory.JUNK

    def test_unknown_sender_direct_with_deadline_is_high(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(
            from_addr="stranger@company.com",
            to_addr="jpastore79@gmail.com",
            subject="Please respond by Friday deadline",
        )
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert result.category in (MessageCategory.CRITICAL, MessageCategory.HIGH)

    def test_cc_on_mailing_list_is_low(self, scorer: ImportanceScorer) -> None:
        msg = _make_msg(
            from_addr="someone@list.org",
            to_addr="dev-list@groups.example.com",
            extra_headers=[
                {"name": "List-Id", "value": "<dev-list.groups.example.com>"},
                {"name": "Cc", "value": "jpastore79@gmail.com"},
            ],
        )
        result = scorer.score_message(msg, "jpastore79@gmail.com")
        assert result.category in (MessageCategory.LOW, MessageCategory.JUNK)
