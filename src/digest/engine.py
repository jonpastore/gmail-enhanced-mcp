"""DigestEngine: assembles structured email digest from existing triage components."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from ..calendar.date_parser import DateParser
from ..triage.engine import ImportanceScorer, JunkDetector
from ..triage.tracker import FollowUpTracker


class DigestItem(BaseModel):
    """A single message item in the digest summary."""

    message_id: str
    from_addr: str
    subject: str
    category: str
    score: float
    link: str


class DigestSummary(BaseModel):
    """Aggregate counts and top items for the digest."""

    total_unread: int
    by_category: dict[str, int]
    top_items: list[DigestItem]


class DigestActionable(BaseModel):
    """Actionable sections of the digest."""

    needs_reply: list[dict[str, Any]] = []
    deadlines: list[dict[str, Any]] = []
    overdue_followups: list[dict[str, Any]] = []
    calendar_conflicts: list[dict[str, Any]] = []


class DigestResult(BaseModel):
    """Full digest output for one account and period."""

    account: str
    period: str
    generated_at: str
    summary: DigestSummary
    actionable: DigestActionable
    sent: bool = False


def _make_link(message_id: str, provider: str) -> str:
    """Generate a deep link to the message in the provider's web UI.

    Args:
        message_id: The provider message ID.
        provider: Either "gmail" or "outlook".

    Returns:
        URL string, or empty string for unknown providers.
    """
    if provider == "gmail":
        return f"https://mail.google.com/mail/u/0/#inbox/{message_id}"
    if provider == "outlook":
        return f"https://outlook.live.com/mail/0/id/{message_id}"
    return ""


def _get_headers(msg: dict[str, Any]) -> dict[str, str]:
    """Extract headers from a Gmail-format message dict.

    Args:
        msg: Gmail-format message dictionary.

    Returns:
        Dict mapping lowercased header names to values.
    """
    payload = msg.get("payload", {})
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _detect_provider(account: str) -> str:
    """Infer email provider from account address.

    Args:
        account: Account email address.

    Returns:
        "gmail", "outlook", or "gmail" as default.
    """
    lower = account.lower()
    if lower.endswith("@gmail.com") or lower.endswith("@googlemail.com"):
        return "gmail"
    if (
        lower.endswith("@outlook.com")
        or lower.endswith("@hotmail.com")
        or lower.endswith("@live.com")
    ):
        return "outlook"
    return "gmail"


class DigestEngine:
    """Orchestrates data assembly for a per-account email digest."""

    def __init__(
        self,
        client: Any,
        cache: Any,
        calendar_ctx: Any | None = None,
    ) -> None:
        """Initialise DigestEngine.

        Args:
            client: EmailClient instance with search_messages / read_message methods.
            cache: TriageCache instance for scorer and tracker.
            calendar_ctx: Optional CalendarContext for schedule-aware scoring.
        """
        self._client = client
        self._cache = cache
        self._calendar_ctx = calendar_ctx

    def generate(self, period: str = "daily", max_results: int = 100) -> DigestResult:
        """Generate a digest for the client's account.

        Fetches unread messages, scores them all, assembles summary and
        actionable sections, and returns a DigestResult.

        Args:
            period: "daily" or "weekly".
            max_results: Maximum number of unread messages to fetch.

        Returns:
            DigestResult populated with summary and actionable data.
        """
        account = self._client.email_address
        provider = _detect_provider(account)
        generated_at = datetime.now(tz=UTC).isoformat()

        messages = self._fetch_messages(max_results)
        scores = ImportanceScorer(self._cache, calendar_ctx=self._calendar_ctx).score_messages(
            messages, account
        )

        score_by_id = {s.message_id: s for s in scores}
        by_category: dict[str, int] = {"critical": 0, "high": 0, "normal": 0, "low": 0, "junk": 0}
        for s in scores:
            cat = str(s.category).lower()
            by_category[cat] = by_category.get(cat, 0) + 1

        top_scores = scores[:10]
        msg_by_id = {m.get("id", ""): m for m in messages}
        top_items = self._build_top_items(top_scores, msg_by_id, provider)

        needs_reply = self._find_needs_reply(messages, account, score_by_id, provider)
        deadlines = self._find_deadlines(top_scores, msg_by_id, provider)
        overdue = self._find_overdue_followups(account, provider)
        calendar_conflicts = self._find_calendar_conflicts(period)

        return DigestResult(
            account=account,
            period=period,
            generated_at=generated_at,
            summary=DigestSummary(
                total_unread=len(messages),
                by_category=by_category,
                top_items=top_items,
            ),
            actionable=DigestActionable(
                needs_reply=needs_reply,
                deadlines=deadlines,
                overdue_followups=overdue,
                calendar_conflicts=calendar_conflicts,
            ),
        )

    def _fetch_messages(self, max_results: int) -> list[dict[str, Any]]:
        """Fetch and read unread messages in batches of 10.

        Args:
            max_results: Maximum number of messages to retrieve.

        Returns:
            List of full message dicts.
        """
        result = self._client.search_messages(q="is:unread", max_results=max_results)
        stubs: list[dict[str, Any]] = result.get("messages", [])
        messages: list[dict[str, Any]] = []
        batch_size = 10
        for i in range(0, len(stubs), batch_size):
            if i > 0:
                time.sleep(0.1)
            for stub in stubs[i : i + batch_size]:
                try:
                    msg = self._client.read_message(stub["id"])
                    messages.append(msg)
                except Exception:
                    continue
        return messages

    def _build_top_items(
        self,
        top_scores: list[Any],
        msg_by_id: dict[str, dict[str, Any]],
        provider: str,
    ) -> list[DigestItem]:
        """Build DigestItem list from top scored messages.

        Args:
            top_scores: ImportanceScore objects, already sorted by score desc.
            msg_by_id: Message dicts keyed by message ID.
            provider: Email provider for deep link generation.

        Returns:
            List of DigestItem.
        """
        items: list[DigestItem] = []
        for score in top_scores:
            msg = msg_by_id.get(score.message_id, {})
            headers = _get_headers(msg)
            items.append(
                DigestItem(
                    message_id=score.message_id,
                    from_addr=headers.get("from", ""),
                    subject=headers.get("subject", "(no subject)"),
                    category=str(score.category).lower(),
                    score=score.score,
                    link=_make_link(score.message_id, provider),
                )
            )
        return items

    def _find_needs_reply(
        self,
        messages: list[dict[str, Any]],
        account: str,
        score_by_id: dict[str, Any],
        provider: str,
    ) -> list[dict[str, Any]]:
        """Find messages that likely need a reply.

        Criteria: direct To: recipient, last message not from account,
        contains a question mark, and not junk. Requires at least 2 signals.

        Args:
            messages: Full message dicts.
            account: Account email address.
            score_by_id: ImportanceScore keyed by message ID.
            provider: Email provider for deep link generation.

        Returns:
            List of dicts with message_id, from, subject, reason, link.
        """
        junk_detector = JunkDetector()
        account_lower = account.lower()
        qualifying: list[dict[str, Any]] = []

        for msg in messages:
            msg_id = msg.get("id", "")
            score = score_by_id.get(msg_id)
            if score and str(score.category).lower() == "junk":
                continue

            headers = _get_headers(msg)
            to_raw = headers.get("to", "").lower()
            subject = headers.get("subject", "")
            snippet = msg.get("snippet", "")

            reasons: list[str] = []

            if account_lower in to_raw:
                reasons.append("You are in To:")

            from_addr = headers.get("from", "")
            if account_lower not in from_addr.lower():
                reasons.append("Last message not from you")

            if "?" in subject or "?" in snippet:
                reasons.append("Contains question")

            junk = junk_detector.analyze(msg)
            if not junk.is_junk:
                reasons.append("Not junk")

            if len(reasons) >= 2:
                qualifying.append(
                    {
                        "message_id": msg_id,
                        "from": from_addr,
                        "subject": subject,
                        "reason": "; ".join(reasons),
                        "link": _make_link(msg_id, provider),
                    }
                )

        return qualifying

    def _find_deadlines(
        self,
        top_scores: list[Any],
        msg_by_id: dict[str, dict[str, Any]],
        provider: str,
    ) -> list[dict[str, Any]]:
        """Extract deadlines from top-scored message subjects and snippets.

        Args:
            top_scores: Top ImportanceScore objects.
            msg_by_id: Message dicts keyed by message ID.
            provider: Email provider for deep link generation.

        Returns:
            List of dicts with message_id, subject, deadline_date, context, link.
        """
        date_parser = DateParser()
        deadlines: list[dict[str, Any]] = []

        for score in top_scores:
            msg = msg_by_id.get(score.message_id, {})
            headers = _get_headers(msg)
            subject = headers.get("subject", "")
            snippet = msg.get("snippet", "")
            text = f"{subject} {snippet}"

            dates = date_parser.extract_dates(text)
            if dates:
                earliest = min(dates, key=lambda d: d.resolved_date)
                deadlines.append(
                    {
                        "message_id": score.message_id,
                        "subject": subject,
                        "deadline_date": earliest.resolved_date.isoformat(),
                        "context": earliest.raw_text,
                        "link": _make_link(score.message_id, provider),
                    }
                )

        return deadlines

    def _find_overdue_followups(self, account: str, provider: str) -> list[dict[str, Any]]:
        """Retrieve overdue follow-ups from the tracker.

        Args:
            account: Account email address.
            provider: Email provider for deep link generation.

        Returns:
            List of dicts with message_id, thread_id, sent_date, expected_days, link.
        """
        try:
            overdue = FollowUpTracker(self._cache).get_overdue(account)
        except Exception:
            return []

        return [
            {
                "message_id": fu.message_id,
                "thread_id": fu.thread_id,
                "sent_date": fu.sent_date.isoformat(),
                "expected_days": fu.expected_reply_days,
                "link": _make_link(fu.message_id, provider),
            }
            for fu in overdue
        ]

    def _find_calendar_conflicts(self, period: str) -> list[dict[str, Any]]:
        """Get today's calendar events for the conflicts section.

        Only populated when calendar_ctx is available and period is "daily".

        Args:
            period: Digest period; only "daily" triggers calendar lookup.

        Returns:
            List of event dicts, or empty list.
        """
        if self._calendar_ctx is None or period != "daily":
            return []
        try:
            events = self._calendar_ctx.get_today_events()
            return list(events) if events else []
        except Exception:
            return []
