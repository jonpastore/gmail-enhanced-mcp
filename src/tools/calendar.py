"""Calendar-aware email intelligence tool handlers."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

from ..calendar.context import CalendarContext, ConflictResult, MeetingPrepContext
from ..calendar.date_parser import DateParser
from ..email_client import EmailClient
from ..triage.cache import TriageCache
from ..triage.engine import ImportanceScorer
from ..triage.models import GmailMCPError


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _error_content(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Error: {msg}"}], "isError": True}


def handle_check_email_conflicts(
    args: dict[str, Any],
    client: EmailClient,
    calendar_ctx: CalendarContext,
    cache: TriageCache,
) -> dict[str, Any]:
    """Scan emails for date mentions and cross-reference against calendar.

    Args:
        args: Tool arguments with optional q, maxResults, daysAhead.
        client: Email client for searching messages.
        calendar_ctx: Calendar context for event lookups.
        cache: Triage cache (unused, required by signature).

    Returns:
        MCP content with conflict results.
    """
    try:
        q = args.get("q")
        max_results = args.get("maxResults", 10)
        days_ahead = args.get("daysAhead", 7)

        search_result = client.search_messages(q=q, max_results=max_results)
        message_stubs = search_result.get("messages", [])

        if not message_stubs:
            return _text_content("No messages found to check for conflicts.")

        parser = DateParser()
        ref_date = date.today()
        conflicts: list[ConflictResult] = []

        for stub in message_stubs:
            msg = client.read_message(stub["id"])
            headers = _extract_headers(msg)
            subject = headers.get("subject", "")
            snippet = msg.get("snippet", "")
            text = f"{subject} {snippet}"

            mentions = parser.extract_dates(text, reference_date=ref_date)
            for mention in mentions:
                if mention.resolved_date < ref_date:
                    continue
                if (mention.resolved_date - ref_date).days > days_ahead:
                    continue

                events = calendar_ctx.get_events_for_date(mention.resolved_date)
                if events:
                    severity = "hard_conflict" if len(events) >= 3 else "busy_day"
                    conflicts.append(
                        ConflictResult(
                            email_message_id=msg.get("id", ""),
                            date_mention=mention.model_dump(),
                            conflicting_events=events,
                            severity=severity,
                        )
                    )

        if not conflicts:
            return _text_content("No scheduling conflicts found.")

        lines = [f"Found {len(conflicts)} potential conflict(s):", ""]
        for c in conflicts:
            dm = c.date_mention
            raw = dm.get("raw_text", "") if isinstance(dm, dict) else str(dm)
            lines.append(f"  Email {c.email_message_id}: mentions '{raw}'")
            lines.append(f"    Severity: {c.severity}")
            lines.append(f"    Conflicting events ({len(c.conflicting_events)}):")
            for ev in c.conflicting_events:
                lines.append(
                    f"      - {ev.summary} "
                    f"({ev.start.strftime('%I:%M %p')} - {ev.end.strftime('%I:%M %p')})"
                )
            lines.append("")

        return _text_content("\n".join(lines))
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Conflict check failed: {type(exc).__name__}: {exc}")


def handle_meeting_prep(
    args: dict[str, Any],
    client: EmailClient,
    calendar_ctx: CalendarContext,
    cache: TriageCache,
) -> dict[str, Any]:
    """Surface relevant email threads for an upcoming calendar event.

    Args:
        args: Tool arguments with optional eventId, hoursAhead.
        client: Email client for searching threads.
        calendar_ctx: Calendar context for event lookups.
        cache: Triage cache (unused, required by signature).

    Returns:
        MCP content with meeting prep context.
    """
    try:
        hours_ahead = args.get("hoursAhead", 4)
        today_events = calendar_ctx.get_today_events()

        if not today_events:
            return _text_content("No meetings found today.")

        now = datetime.now().astimezone()
        upcoming = [
            ev
            for ev in today_events
            if not ev.is_all_day
            and ev.start > now
            and (ev.start - now).total_seconds() < hours_ahead * 3600
        ]

        event_id = args.get("eventId")
        if event_id:
            target_events = [ev for ev in today_events if ev.event_id == event_id]
            if not target_events:
                return _error_content(f"Event {event_id} not found in today's calendar.")
            upcoming = target_events

        if not upcoming:
            return _text_content(f"No meetings in the next {hours_ahead} hours.")

        results: list[MeetingPrepContext] = []
        for ev in upcoming:
            attendee_emails = [e for e in ev.attendee_emails if e]
            related_threads: list[dict[str, Any]] = []

            for email_addr in attendee_emails[:5]:
                search_result = client.search_messages(q=f"from:{email_addr}", max_results=3)
                threads = search_result.get("messages", [])
                for t in threads[:2]:
                    related_threads.append(
                        {"thread_id": t.get("threadId", ""), "message_id": t.get("id", "")}
                    )

            results.append(
                MeetingPrepContext(
                    event=ev,
                    related_threads=related_threads,
                    attendee_match_count=len(attendee_emails),
                )
            )

        lines = [f"Meeting Prep ({len(results)} upcoming):", ""]
        for prep in results:
            ev = prep.event
            lines.append(f"  {ev.summary}")
            lines.append(
                f"    Time: {ev.start.strftime('%I:%M %p')} - {ev.end.strftime('%I:%M %p')}"
            )
            if ev.location:
                lines.append(f"    Location: {ev.location}")
            lines.append(f"    Attendees: {prep.attendee_match_count}")
            if prep.related_threads:
                lines.append(f"    Related threads: {len(prep.related_threads)}")
                for t in prep.related_threads[:5]:
                    lines.append(f"      - Thread {t['thread_id']}")
            lines.append("")

        return _text_content("\n".join(lines))
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Meeting prep failed: {type(exc).__name__}: {exc}")


def handle_today_briefing(
    args: dict[str, Any],
    client: EmailClient,
    calendar_ctx: CalendarContext,
    cache: TriageCache,
) -> dict[str, Any]:
    """Combined inbox triage + calendar overview for the day.

    Delegates to ImportanceScorer for triage (does NOT re-implement scoring).
    Appends calendar section with today's events.

    Args:
        args: Tool arguments with optional includeCalendar, maxEmails.
        client: Email client for searching messages.
        calendar_ctx: Calendar context for today's events.
        cache: Triage cache for scoring.

    Returns:
        MCP content with briefing.
    """
    try:
        include_calendar = args.get("includeCalendar", True)
        max_emails = args.get("maxEmails", 20)

        search_result = client.search_messages(q="is:unread", max_results=max_emails)
        message_stubs = search_result.get("messages", [])

        lines: list[str] = ["Today's Briefing", "=" * 40, ""]

        if include_calendar:
            events = calendar_ctx.get_today_events()
            if events:
                lines.append(f"Calendar ({len(events)} events):")
                for ev in events:
                    if ev.is_all_day:
                        lines.append(f"  All day: {ev.summary}")
                    else:
                        lines.append(
                            f"  {ev.start.strftime('%I:%M %p')} - "
                            f"{ev.end.strftime('%I:%M %p')}: {ev.summary}"
                        )
                lines.append("")
            else:
                lines.append("Calendar: No events today.")
                lines.append("")

        if not message_stubs:
            lines.append("Inbox: No unread messages.")
            return _text_content("\n".join(lines))

        messages: list[dict[str, Any]] = []
        batch_size = 10
        for i in range(0, len(message_stubs), batch_size):
            if i > 0:
                time.sleep(0.1)
            batch = message_stubs[i : i + batch_size]
            for stub in batch:
                msg = client.read_message(stub["id"])
                messages.append(msg)

        scorer = ImportanceScorer(cache, calendar_ctx=calendar_ctx)
        account = client.email_address
        scores = scorer.score_messages(messages, account)

        lines.append(f"Inbox ({len(scores)} unread):")
        for sc in scores:
            lines.append(f"  {sc.message_id}: {sc.score:.2f} ({sc.category.value})")

        return _text_content("\n".join(lines))
    except GmailMCPError:
        raise
    except Exception as exc:
        return _error_content(f"Briefing failed: {type(exc).__name__}: {exc}")


def _extract_headers(msg: dict[str, Any]) -> dict[str, str]:
    payload = msg.get("payload", {})
    raw_headers = payload.get("headers", [])
    return {h["name"].lower(): h["value"] for h in raw_headers}
