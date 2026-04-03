"""Digest formatters: HTML email body and plain-text fallback."""

from __future__ import annotations

from .engine import DigestResult

_CATEGORY_COLORS: dict[str, str] = {
    "critical": "#dc3545",
    "high": "#fd7e14",
    "normal": "#28a745",
    "low": "#6c757d",
    "junk": "#adb5bd",
}

_BASE_STYLE = (
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;"
    " font-size: 14px; color: #212529; max-width: 680px; margin: 0 auto; padding: 20px;"
)

_H2_STYLE = "color: #1a1a1a; margin-bottom: 4px;"
_H3_STYLE = (
    "color: #343a40; margin-top: 24px; margin-bottom: 8px;"
    " border-bottom: 1px solid #dee2e6; padding-bottom: 4px;"
)
_LINK_STYLE = "color: #1a73e8; text-decoration: none;"
_MUTED_STYLE = "color: #6c757d;"
_ITEM_STYLE = "margin-bottom: 8px;"


def _badge(category: str) -> str:
    """Render an inline HTML badge for a message category.

    Args:
        category: Lowercase category name.

    Returns:
        HTML span string with inline styles.
    """
    color = _CATEGORY_COLORS.get(category.lower(), "#6c757d")
    label = category.upper()
    return (
        f'<span style="background: {color}; color: white; padding: 2px 6px;'
        f' border-radius: 3px; font-size: 11px; font-weight: bold;">{label}</span>'
    )


def _linked(href: str, text: str) -> str:
    """Render a hyperlink.

    Args:
        href: Target URL.
        text: Display text.

    Returns:
        HTML anchor string.
    """
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="{href}" style="{_LINK_STYLE}">{safe}</a>'


def _category_summary_line(by_category: dict[str, int]) -> str:
    """Format category counts as a readable summary line.

    Args:
        by_category: Dict mapping category name to count.

    Returns:
        Human-readable string like "Critical: 2 | High: 5 | Normal: 28".
    """
    order = ["critical", "high", "normal", "low", "junk"]
    parts = [f"{k.capitalize()}: {by_category.get(k, 0)}" for k in order]
    return " | ".join(parts)


def format_digest_html(result: DigestResult) -> str:
    """Generate a clean HTML email body for the digest.

    Uses inline CSS throughout for email client compatibility.

    Args:
        result: DigestResult containing all digest data.

    Returns:
        Complete HTML string suitable for use as an email body.
    """
    sections: list[str] = []

    sections.append(f'<div style="{_BASE_STYLE}">')

    sections.append(f'<h2 style="{_H2_STYLE}">Daily Digest \u2014 {result.account}</h2>')
    sections.append(
        f'<p style="{_MUTED_STYLE}">{result.generated_at[:10]} | '
        f"{result.summary.total_unread} unread</p>"
    )

    sections.append(f'<h3 style="{_H3_STYLE}">Summary</h3>')
    sections.append(f"<p>{_category_summary_line(result.summary.by_category)}</p>")

    sections.append(f'<h3 style="{_H3_STYLE}">Top Items</h3>')
    if result.summary.top_items:
        sections.append("<ul>")
        for item in result.summary.top_items:
            badge = _badge(item.category)
            link = _linked(item.link, item.subject) if item.link else item.subject
            from_part = f' <span style="{_MUTED_STYLE}">\u2014 {item.from_addr}</span>'
            sections.append(f'  <li style="{_ITEM_STYLE}">{badge} {link}{from_part}</li>')
        sections.append("</ul>")
    else:
        sections.append("<p>All clear \u2014 no unread messages.</p>")

    needs_reply = result.actionable.needs_reply
    sections.append(f'<h3 style="{_H3_STYLE}">Needs Your Reply ({len(needs_reply)})</h3>')
    if needs_reply:
        sections.append("<ul>")
        for nr_item in needs_reply:
            msg_id = nr_item.get("message_id", "")
            link_url = nr_item.get("link", "")
            subject = nr_item.get("subject", "(no subject)")
            from_addr = nr_item.get("from", "")
            reason = nr_item.get("reason", "")
            link = _linked(link_url, subject) if link_url else subject
            from_part = (
                f' <span style="{_MUTED_STYLE}">\u2014 {from_addr}</span>' if from_addr else ""
            )
            reason_part = (
                f' <span style="color: #868e96; font-size: 12px;">({reason})</span>'
                if reason
                else ""
            )
            sections.append(f'  <li style="{_ITEM_STYLE}">{link}{from_part}{reason_part}</li>')
            _ = msg_id
        sections.append("</ul>")
    else:
        sections.append("<p>No messages need your reply.</p>")

    deadlines = result.actionable.deadlines
    sections.append(f'<h3 style="{_H3_STYLE}">Follow-up Deadlines</h3>')
    if deadlines:
        sections.append("<ul>")
        for dl_item in deadlines:
            link_url = dl_item.get("link", "")
            subject = dl_item.get("subject", "(no subject)")
            deadline_date = dl_item.get("deadline_date", "")
            link = _linked(link_url, subject) if link_url else subject
            date_part = f' <span style="{_MUTED_STYLE}">\u2014 deadline {deadline_date}</span>'
            sections.append(f'  <li style="{_ITEM_STYLE}">{link}{date_part}</li>')
        sections.append("</ul>")
    else:
        sections.append("<p>No upcoming deadlines found.</p>")

    overdue = result.actionable.overdue_followups
    sections.append(f'<h3 style="{_H3_STYLE}">Overdue Follow-ups</h3>')
    if overdue:
        sections.append("<ul>")
        for od_item in overdue:
            link_url = od_item.get("link", "")
            msg_id = od_item.get("message_id", "")
            sent_date = od_item.get("sent_date", "")
            expected_days = od_item.get("expected_days", "")
            display = msg_id[:12] + "\u2026" if len(msg_id) > 12 else msg_id
            link = _linked(link_url, display) if link_url else display
            meta = (
                f' <span style="{_MUTED_STYLE}">'
                f"\u2014 sent {sent_date[:10]}, expected reply in {expected_days}d"
                f"</span>"
            )
            sections.append(f'  <li style="{_ITEM_STYLE}">{link}{meta}</li>')
        sections.append("</ul>")
    else:
        sections.append("<p>No overdue follow-ups.</p>")

    calendar = result.actionable.calendar_conflicts
    if calendar:
        sections.append(f'<h3 style="{_H3_STYLE}">Calendar Today</h3>')
        sections.append("<ul>")
        for event in calendar:
            title = str(event.get("summary", event.get("title", "Event")))
            start = str(event.get("start", ""))
            safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            start_part = f' <span style="{_MUTED_STYLE}">@ {start}</span>' if start else ""
            sections.append(f'  <li style="{_ITEM_STYLE}">{safe_title}{start_part}</li>')
        sections.append("</ul>")

    sections.append(
        '<hr style="border: none; border-top: 1px solid #dee2e6; margin-top: 32px;">'
        '<p style="color: #adb5bd; font-size: 11px;">Generated by Gmail Enhanced MCP</p>'
    )
    sections.append("</div>")

    return "\n".join(sections)


def format_digest_text(result: DigestResult) -> str:
    """Generate a plain-text fallback digest.

    Same content as the HTML version but formatted as readable plain text
    with URLs included inline.

    Args:
        result: DigestResult containing all digest data.

    Returns:
        Plain-text string suitable for email or terminal output.
    """
    lines: list[str] = []

    lines.append(f"Daily Digest -- {result.account}")
    lines.append(f"{result.generated_at[:10]} | {result.summary.total_unread} unread")
    lines.append("")

    lines.append("=== Summary ===")
    lines.append(_category_summary_line(result.summary.by_category))
    lines.append("")

    lines.append("=== Top Items ===")
    if result.summary.top_items:
        for item in result.summary.top_items:
            cat = item.category.upper()
            lines.append(f"[{cat}] {item.subject} -- {item.from_addr}")
            if item.link:
                lines.append(f"  {item.link}")
    else:
        lines.append("All clear -- no unread messages.")
    lines.append("")

    needs_reply = result.actionable.needs_reply
    lines.append(f"=== Needs Your Reply ({len(needs_reply)}) ===")
    if needs_reply:
        for nr_item in needs_reply:
            lines.append(f"{nr_item.get('subject', '(no subject)')} -- {nr_item.get('from', '')}")
            lines.append(f"  Reason: {nr_item.get('reason', '')}")
            if nr_item.get("link"):
                lines.append(f"  {nr_item['link']}")
    else:
        lines.append("No messages need your reply.")
    lines.append("")

    deadlines = result.actionable.deadlines
    lines.append("=== Follow-up Deadlines ===")
    if deadlines:
        for dl_item in deadlines:
            subj = dl_item.get("subject", "(no subject)")
            dl_date = dl_item.get("deadline_date", "")
            lines.append(f"{subj} -- deadline {dl_date}")
            if dl_item.get("link"):
                lines.append(f"  {dl_item['link']}")
    else:
        lines.append("No upcoming deadlines found.")
    lines.append("")

    overdue = result.actionable.overdue_followups
    lines.append("=== Overdue Follow-ups ===")
    if overdue:
        for od_item in overdue:
            msg_id = od_item.get("message_id", "")
            lines.append(
                f"{msg_id} -- sent {str(od_item.get('sent_date', ''))[:10]},"
                f" expected reply in {od_item.get('expected_days', '')}d"
            )
            if od_item.get("link"):
                lines.append(f"  {od_item['link']}")
    else:
        lines.append("No overdue follow-ups.")
    lines.append("")

    calendar = result.actionable.calendar_conflicts
    if calendar:
        lines.append("=== Calendar Today ===")
        for event in calendar:
            title = str(event.get("summary", event.get("title", "Event")))
            start = str(event.get("start", ""))
            entry = title
            if start:
                entry += f" @ {start}"
            lines.append(entry)
        lines.append("")

    lines.append("--")
    lines.append("Generated by Gmail Enhanced MCP")

    return "\n".join(lines)
