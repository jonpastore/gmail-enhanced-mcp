"""Importance scoring engine and junk detection for email triage."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from .cache import TriageCache
from .models import (
    ImportanceScore,
    JunkSignal,
    MessageCategory,
    PrioritySender,
    ScoringSignal,
    SenderTier,
)

_DEFAULT_WEIGHTS: dict[str, float] = {
    "priority_sender_critical": 0.55,
    "priority_sender_high": 0.25,
    "direct_recipient": 0.15,
    "is_reply_to_me": 0.15,
    "has_deadline": 0.25,
    "has_attachment": 0.05,
    "recent_24h": 0.05,
    "meeting_today_sender": 0.15,
    "junk_detected": -0.50,
}

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "critical": 0.55,
    "high": 0.40,
    "normal": 0.20,
    "low": 0.10,
}

_DEADLINE_PATTERN = re.compile(
    r"(deadline|due\s+date|by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|tomorrow|end\s+of\s+day"
    r"|eod|cob|asap|\d{1,2}[/-]\d{1,2})"
    r"|action\s+required|urgent|time.?sensitive|respond\s+by|please\s+respond\s+by)",
    re.IGNORECASE,
)

_NOREPLY_PATTERN = re.compile(
    r"^(noreply|no-reply|newsletter|marketing)@",
    re.IGNORECASE,
)


class ImportanceScorer:
    """Scores email messages by importance using weighted signals."""

    def __init__(
        self,
        cache: TriageCache,
        config_path: Path | None = None,
        calendar_ctx: Any | None = None,
    ) -> None:
        """Load scoring weights from config JSON or use defaults.

        Args:
            cache: TriageCache instance for priority sender lookups.
            config_path: Optional path to scoring config JSON file.
            calendar_ctx: Optional CalendarContext for schedule-aware scoring.
        """
        self._cache = cache
        self._calendar_ctx = calendar_ctx
        self._weights = dict(_DEFAULT_WEIGHTS)
        self._thresholds = dict(_DEFAULT_THRESHOLDS)
        self._junk_detector = JunkDetector()
        self._priority_senders: list[PrioritySender] = []
        self._load_config(config_path)
        self._load_priority_senders()

    def score_message(self, msg: dict[str, Any], account: str) -> ImportanceScore:
        """Score a single message dict.

        Args:
            msg: Gmail-format message dictionary.
            account: Account email address for context.

        Returns:
            ImportanceScore with computed score, signals, and category.
        """
        signals = self._extract_signals(msg, account)
        raw_score = sum(s.weight for s in signals)
        score = round(max(0.0, min(1.0, raw_score)), 10)
        category = self._compute_category(score, signals)
        return ImportanceScore(
            message_id=msg.get("id", ""),
            thread_id=msg.get("threadId", ""),
            score=score,
            signals=signals,
            category=category,
        )

    def score_messages(self, messages: list[dict[str, Any]], account: str) -> list[ImportanceScore]:
        """Batch score messages. Returns sorted by score descending.

        Primes calendar context once before scoring loop if available.

        Args:
            messages: List of Gmail-format message dicts.
            account: Account email address for context.

        Returns:
            List of ImportanceScore sorted by score descending.
        """
        if self._calendar_ctx is not None:
            from datetime import date

            self._calendar_ctx.prime_for_date(date.today())
        scores = [self.score_message(msg, account) for msg in messages]
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def _load_config(self, config_path: Path | None) -> None:
        """Load weights and thresholds from a JSON config file."""
        if config_path is None:
            default_path = Path(__file__).parent.parent.parent / "data" / "triage_config.json"
            if default_path.exists():
                config_path = default_path
        if config_path is None or not config_path.exists():
            return
        try:
            data = json.loads(config_path.read_text())
            if "weights" in data:
                self._weights.update(data["weights"])
            if "thresholds" in data:
                self._thresholds.update(data["thresholds"])
        except (json.JSONDecodeError, OSError):
            pass

    def _load_priority_senders(self) -> None:
        """Refresh priority senders from cache."""
        self._priority_senders = self._cache.get_priority_senders()

    def _extract_signals(self, msg: dict[str, Any], account: str) -> list[ScoringSignal]:
        """Extract all scoring signals from a message."""
        signals: list[ScoringSignal] = []
        headers = self.extract_headers(msg)
        from_addr = headers.get("from", "")
        to_raw = headers.get("to", "")
        to_addrs = [addr.strip() for addr in to_raw.split(",")]

        extractors = [
            lambda: self._signal_priority_sender(from_addr),
            lambda: self._signal_direct_recipient(to_addrs, account),
            lambda: self._signal_has_deadline(msg),
            lambda: self._signal_is_reply_to_me(msg, account),
            lambda: self._signal_has_attachment(msg),
            lambda: self._signal_meeting_today_sender(from_addr),
            lambda: self._signal_junk_detected(msg),
            lambda: self._signal_recent(msg),
        ]
        for extractor in extractors:
            signal = extractor()
            if signal is not None:
                signals.append(signal)
        return signals

    def _signal_priority_sender(self, from_addr: str) -> ScoringSignal | None:
        """Check if sender is a priority sender."""
        for ps in self._priority_senders:
            pattern = ps.email_pattern
            if pattern.startswith("*@"):
                domain = pattern[2:]
                if from_addr.lower().endswith(f"@{domain.lower()}"):
                    return self._make_priority_signal(ps)
            elif from_addr.lower() == pattern.lower():
                return self._make_priority_signal(ps)
        return None

    def _make_priority_signal(self, ps: PrioritySender) -> ScoringSignal:
        """Create a scoring signal for a priority sender match."""
        if ps.tier == SenderTier.CRITICAL:
            return ScoringSignal(
                name="priority_sender_critical",
                weight=self._weights.get("priority_sender_critical", 0.55),
                detail=f"Priority sender: {ps.label} (critical)",
            )
        return ScoringSignal(
            name="priority_sender_high",
            weight=self._weights.get("priority_sender_high", 0.25),
            detail=f"Priority sender: {ps.label} (high)",
        )

    def _signal_direct_recipient(self, to_addrs: list[str], account: str) -> ScoringSignal | None:
        """Check if account is a direct (To:) recipient."""
        for addr in to_addrs:
            if addr.lower() == account.lower():
                return ScoringSignal(
                    name="direct_recipient",
                    weight=self._weights.get("direct_recipient", 0.15),
                    detail="Direct recipient in To: field",
                )
        return None

    def _signal_has_deadline(self, msg: dict[str, Any]) -> ScoringSignal | None:
        """Check subject for deadline-related keywords."""
        headers = self.extract_headers(msg)
        subject = headers.get("subject", "")
        if _DEADLINE_PATTERN.search(subject):
            return ScoringSignal(
                name="has_deadline",
                weight=self._weights.get("has_deadline", 0.25),
                detail="Subject contains deadline-related keywords",
            )
        return None

    def _signal_is_reply_to_me(self, msg: dict[str, Any], account: str) -> ScoringSignal | None:
        """Check if message is a reply (has In-Reply-To or References header)."""
        headers = self.extract_headers(msg)
        has_reply_header = bool(headers.get("in-reply-to") or headers.get("references"))
        if has_reply_header:
            return ScoringSignal(
                name="is_reply_to_me",
                weight=self._weights.get("is_reply_to_me", 0.15),
                detail="Message is a reply in a thread",
            )
        return None

    def _signal_has_attachment(self, msg: dict[str, Any]) -> ScoringSignal | None:
        """Check if message has non-text attachments."""
        parts = msg.get("payload", {}).get("parts", [])
        for part in parts:
            mime = part.get("mimeType", "")
            if mime and not mime.startswith("text/") and not mime.startswith("multipart/"):
                return ScoringSignal(
                    name="has_attachment",
                    weight=self._weights.get("has_attachment", 0.05),
                    detail="Message has file attachment",
                )
        return None

    def _signal_meeting_today_sender(self, from_addr: str) -> ScoringSignal | None:
        """Check if sender is an attendee of today's/tomorrow's meetings."""
        if self._calendar_ctx is None:
            return None
        if self._calendar_ctx.is_meeting_attendee(from_addr):
            return ScoringSignal(
                name="meeting_today_sender",
                weight=self._weights.get("meeting_today_sender", 0.15),
                detail="Sender is attendee of upcoming meeting",
            )
        return None

    def _signal_junk_detected(self, msg: dict[str, Any]) -> ScoringSignal | None:
        """Check if message triggers junk detection."""
        junk = self._junk_detector.analyze(msg)
        if junk.is_junk:
            return ScoringSignal(
                name="junk_detected",
                weight=self._weights.get("junk_detected", -0.50),
                detail=f"Junk signals: {', '.join(junk.reasons)}",
            )
        return None

    def _signal_recent(self, msg: dict[str, Any]) -> ScoringSignal | None:
        """Check if message was received within the last 24 hours."""
        headers = self.extract_headers(msg)
        date_str = headers.get("date", "")
        if not date_str:
            return None
        try:
            msg_date = parsedate_to_datetime(date_str)
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=UTC)
            now = datetime.now(tz=UTC)
            if (now - msg_date).total_seconds() < 86400:
                return ScoringSignal(
                    name="recent_24h",
                    weight=self._weights.get("recent_24h", 0.05),
                    detail="Message received within last 24 hours",
                )
        except (ValueError, TypeError):
            pass
        return None

    def _compute_category(self, score: float, signals: list[ScoringSignal]) -> MessageCategory:
        """Determine message category from score and thresholds."""
        if score >= self._thresholds["critical"]:
            return MessageCategory.CRITICAL
        if score >= self._thresholds["high"]:
            return MessageCategory.HIGH
        if score >= self._thresholds["normal"]:
            return MessageCategory.NORMAL
        if score >= self._thresholds["low"]:
            return MessageCategory.LOW
        return MessageCategory.JUNK

    @staticmethod
    def extract_headers(msg: dict[str, Any]) -> dict[str, str]:
        """Extract headers from message dict as lowercased-key dict.

        Works for Gmail format where msg["payload"]["headers"] is a list
        of {"name": ..., "value": ...} dicts.

        Args:
            msg: Gmail-format message dictionary.

        Returns:
            Dict mapping lowercased header names to values.
        """
        payload = msg.get("payload", {})
        raw_headers = payload.get("headers", [])
        return {h["name"].lower(): h["value"] for h in raw_headers}


class JunkDetector:
    """Detects junk/bulk email using header analysis."""

    def analyze(self, msg: dict[str, Any]) -> JunkSignal:
        """Analyze message for junk signals using headers only.

        Args:
            msg: Gmail-format message dictionary.

        Returns:
            JunkSignal with detection result and confidence.
        """
        headers = ImportanceScorer.extract_headers(msg)
        from_addr = headers.get("from", "")
        reasons: list[str] = []

        if self._check_unsubscribe_header(headers):
            reasons.append("has_unsubscribe_header")
        if self._check_precedence_bulk(headers):
            reasons.append("precedence_bulk")
        if self._check_sender_patterns(from_addr):
            reasons.append("noreply_sender")
        if self._check_mailing_list_headers(headers):
            reasons.append("mailing_list")

        confidence = self._compute_junk_confidence(reasons)
        return JunkSignal(
            message_id=msg.get("id", ""),
            is_junk=len(reasons) > 0,
            confidence=confidence,
            reasons=reasons,
        )

    def _check_unsubscribe_header(self, headers: dict[str, str]) -> bool:
        """Check for List-Unsubscribe header."""
        return "list-unsubscribe" in headers

    def _check_precedence_bulk(self, headers: dict[str, str]) -> bool:
        """Check for Precedence: bulk or list."""
        precedence = headers.get("precedence", "").lower()
        return precedence in ("bulk", "list")

    def _check_sender_patterns(self, from_addr: str) -> bool:
        """Check if sender matches noreply/newsletter/marketing patterns."""
        return bool(_NOREPLY_PATTERN.search(from_addr))

    def _check_mailing_list_headers(self, headers: dict[str, str]) -> bool:
        """Check for List-Id or List-Post headers."""
        return "list-id" in headers or "list-post" in headers

    def _compute_junk_confidence(self, reasons: list[str]) -> float:
        """Compute junk confidence from number of signals.

        Args:
            reasons: List of junk reason strings.

        Returns:
            Confidence float: 0 signals=0.0, 1=0.4, 2=0.7, 3+=0.9.
        """
        count = len(reasons)
        if count == 0:
            return 0.0
        if count == 1:
            return 0.4
        if count == 2:
            return 0.7
        return 0.9
