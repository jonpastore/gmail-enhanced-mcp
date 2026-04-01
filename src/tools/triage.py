"""Triage tool handlers for inbox scoring, priority senders, and follow-ups."""

from __future__ import annotations

import time
from typing import Any

from ..email_client import EmailClient
from ..triage.cache import TriageCache
from ..triage.engine import ImportanceScorer, JunkDetector
from ..triage.models import (
    AutoSortProposal,
    GmailMCPError,
    MessageCategory,
    SenderTier,
)
from ..triage.priority_senders import PrioritySenderManager
from ..triage.tracker import FollowUpTracker


def _cache_message_metadata(cache: TriageCache, msg: dict[str, Any], account: str) -> None:
    """Cache minimal message metadata so importance_scores FK is satisfied."""
    from ..triage.engine import ImportanceScorer

    headers = ImportanceScorer.extract_headers(msg)
    from_addr = headers.get("from", "")
    to_raw = headers.get("to", "")
    to_addrs = [a.strip() for a in to_raw.split(",")]
    subject = headers.get("subject", "")
    date_str = headers.get("date", "")
    label_ids = ",".join(msg.get("labelIds", []))
    parts = msg.get("payload", {}).get("parts", [])
    has_attachments = any(
        not p.get("mimeType", "").startswith(("text/", "multipart/")) for p in parts
    )
    has_unsub = "list-unsubscribe" in headers
    prec = headers.get("precedence", "").lower()
    has_bulk = prec in ("bulk", "list")

    cache.cache_message_metadata(
        {
            "message_id": msg.get("id", ""),
            "thread_id": msg.get("threadId", ""),
            "account_hash": TriageCache.hash_address(account),
            "from_hash": TriageCache.hash_address(from_addr),
            "to_hashes": ",".join(TriageCache.hash_address(a) for a in to_addrs),
            "subject_hash": TriageCache.hash_address(subject),
            "date_received": date_str,
            "label_ids": label_ids,
            "has_attachments": has_attachments,
            "header_list_unsubscribe": has_unsub,
            "header_precedence_bulk": has_bulk,
            "priority_sender_tier": None,
        }
    )


def _text_content(text: str) -> dict[str, Any]:
    """Return MCP-format text content."""
    return {"content": [{"type": "text", "text": text}]}


def _error_content(msg: str) -> dict[str, Any]:
    """Return MCP-format error content."""
    return {"content": [{"type": "text", "text": f"Error: {msg}"}], "isError": True}


def handle_triage_inbox(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Score, detect junk, and suggest sorting for a batch of messages.

    Args:
        args: Tool arguments with optional q and maxResults.
        client: Email client for searching/reading messages.
        cache: Triage cache for scoring.

    Returns:
        MCP content with scored results.
    """
    try:
        q = args.get("q")
        max_results = args.get("maxResults", 20)
        search_result = client.search_messages(q=q, max_results=max_results)
        message_stubs = search_result.get("messages", [])

        if not message_stubs:
            return _text_content("No messages found.")

        messages: list[dict[str, Any]] = []
        batch_size = 10
        for i in range(0, len(message_stubs), batch_size):
            if i > 0:
                time.sleep(0.1)
            batch = message_stubs[i : i + batch_size]
            for stub in batch:
                msg = client.read_message(stub["id"])
                messages.append(msg)

        scorer = ImportanceScorer(cache)
        junk_detector = JunkDetector()
        account = client.email_address

        scores = scorer.score_messages(messages, account)
        junk_flags = [junk_detector.analyze(msg) for msg in messages]
        junk_map = {jf.message_id: jf for jf in junk_flags}

        proposals: list[AutoSortProposal] = []
        for sc in scores:
            jf = junk_map.get(sc.message_id)
            if jf and jf.is_junk:
                proposals.append(
                    AutoSortProposal(
                        thread_id=sc.thread_id,
                        proposed_label="Junk/Spam",
                        reason="Junk signals detected",
                        confidence=jf.confidence,
                    )
                )
            elif sc.category == MessageCategory.CRITICAL:
                proposals.append(
                    AutoSortProposal(
                        thread_id=sc.thread_id,
                        proposed_label="Priority",
                        reason="Critical importance score",
                        confidence=sc.score,
                    )
                )

        for msg in messages:
            _cache_message_metadata(cache, msg, account)
        for sc in scores:
            cache.store_score(sc)

        lines: list[str] = [f"Triage Results ({len(scores)} messages):"]
        lines.append("")
        for sc in scores:
            jf = junk_map.get(sc.message_id)
            junk_tag = " [JUNK]" if (jf and jf.is_junk) else ""
            lines.append(
                f"  {sc.message_id}: Score: {sc.score:.2f} " f"({sc.category.value}){junk_tag}"
            )
        if proposals:
            lines.append("")
            lines.append("Sort Proposals:")
            for p in proposals:
                lines.append(f"  {p.thread_id} -> {p.proposed_label} ({p.reason})")

        return _text_content("\n".join(lines))
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Triage operation failed: {type(exc).__name__}: {exc}")


def handle_add_priority_sender(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Add an email or domain pattern to the priority sender list.

    Args:
        args: Tool arguments with pattern, tier, and label.
        client: Email client (unused but required by handler signature).
        cache: Triage cache for persistence.

    Returns:
        MCP content with confirmation.
    """
    try:
        pattern = args.get("pattern")
        tier_str = args.get("tier")
        label = args.get("label")

        if not pattern or not tier_str or not label:
            return _error_content("Missing required fields: pattern, tier, label")

        tier = SenderTier(tier_str)
        manager = PrioritySenderManager(cache)
        manager.add(pattern, tier, label)

        return _text_content(f"Added priority sender: {pattern} (tier={tier.value}, label={label})")
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Triage operation failed: {type(exc).__name__}: {exc}")


def handle_list_priority_senders(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """List all priority sender patterns grouped by tier.

    Args:
        args: Tool arguments (none required).
        client: Email client (unused but required by handler signature).
        cache: Triage cache for persistence.

    Returns:
        MCP content with grouped sender list.
    """
    try:
        manager = PrioritySenderManager(cache)
        senders = manager.list_all()

        if not senders:
            return _text_content("No priority senders configured.")

        grouped: dict[str, list[str]] = {}
        for s in senders:
            key = s.tier.value.upper()
            grouped.setdefault(key, [])
            grouped[key].append(f"  {s.email_pattern} ({s.label})")

        lines: list[str] = ["Priority Senders:"]
        for tier_name in ["CRITICAL", "HIGH", "NORMAL"]:
            entries = grouped.get(tier_name, [])
            if entries:
                lines.append(f"\n{tier_name}:")
                lines.extend(entries)

        return _text_content("\n".join(lines))
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Triage operation failed: {type(exc).__name__}: {exc}")


def handle_remove_priority_sender(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Remove a priority sender pattern.

    Args:
        args: Tool arguments with pattern.
        client: Email client (unused but required by handler signature).
        cache: Triage cache for persistence.

    Returns:
        MCP content with success/not-found message.
    """
    try:
        pattern = args.get("pattern", "")
        manager = PrioritySenderManager(cache)
        removed = manager.remove(pattern)

        if removed:
            return _text_content(f"Removed priority sender: {pattern}")
        return _text_content(f"Pattern not found: {pattern}")
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Triage operation failed: {type(exc).__name__}: {exc}")


def handle_track_followup(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Start tracking a sent message for follow-up replies.

    Args:
        args: Tool arguments with messageId and optional expectedDays.
        client: Email client for reading the message.
        cache: Triage cache for persistence.

    Returns:
        MCP content with tracking confirmation.
    """
    try:
        message_id = args.get("messageId", "")
        expected_days = args.get("expectedDays", 3)
        account = client.email_address

        msg = client.read_message(message_id)
        tracker = FollowUpTracker(cache)
        follow_up = tracker.track(msg, account, expected_days=expected_days)

        lines = [
            f"Tracking follow-up for message {follow_up.message_id}",
            f"  Thread: {follow_up.thread_id}",
            f"  Expected reply within: {follow_up.expected_reply_days} days",
        ]
        if follow_up.deadline:
            lines.append(f"  Deadline detected: {follow_up.deadline.isoformat()}")

        return _text_content("\n".join(lines))
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Triage operation failed: {type(exc).__name__}: {exc}")


def handle_check_followups(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Check all tracked follow-ups for replies, overdue items, and deadlines.

    Args:
        args: Tool arguments with optional flags.
        client: Email client for checking thread replies.
        cache: Triage cache for persistence.

    Returns:
        MCP content with structured follow-up report.
    """
    try:
        account = client.email_address
        include_overdue = args.get("includeOverdue", True)
        include_deadline = args.get("includeApproachingDeadline", True)
        within_days = args.get("withinDays", 2)

        tracker = FollowUpTracker(cache)

        replied = tracker.check_replies(client, account)
        lines = ["Follow-Up Report", ""]

        if replied:
            lines.append(f"Replies received ({len(replied)}):")
            for fu in replied:
                lines.append(f"  {fu.message_id} (thread {fu.thread_id})")
            lines.append("")
        else:
            lines.append("No new replies detected.")
            lines.append("")

        if include_overdue:
            overdue = tracker.get_overdue(account)
            if overdue:
                lines.append(f"Overdue ({len(overdue)}):")
                for fu in overdue:
                    lines.append(
                        f"  {fu.message_id} — sent {fu.sent_date.date()}, "
                        f"expected reply in {fu.expected_reply_days}d"
                    )
                lines.append("")
            else:
                lines.append("No overdue follow-ups.")
                lines.append("")

        if include_deadline:
            approaching = tracker.get_approaching_deadline(account, within_days=within_days)
            if approaching:
                lines.append(f"Approaching deadlines ({len(approaching)}):")
                for fu in approaching:
                    dl = fu.deadline.isoformat() if fu.deadline else "unknown"
                    lines.append(f"  {fu.message_id} — deadline {dl}")
                lines.append("")
            else:
                lines.append("No approaching deadlines.")
                lines.append("")

        return _text_content("\n".join(lines))
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Triage operation failed: {type(exc).__name__}: {exc}")


def handle_reset_triage_cache(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Reset the triage cache. Requires confirm=true.

    Args:
        args: Tool arguments with confirm boolean.
        client: Email client (unused but required by handler signature).
        cache: Triage cache to reset.

    Returns:
        MCP content with confirmation or error.
    """
    try:
        if not args.get("confirm"):
            return _error_content("Must set confirm=true to reset triage cache.")

        cache.reset()
        return _text_content("Triage cache has been reset. All cached data deleted.")
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Triage operation failed: {type(exc).__name__}: {exc}")
