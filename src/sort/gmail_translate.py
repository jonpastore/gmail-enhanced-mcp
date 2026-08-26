"""Compile MailRule to Gmail filter JSON and back. No API calls."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .models import MailRule, MailRuleMatch


def to_gmail_filter(rule: MailRule, destination_label_id: str) -> dict[str, Any]:
    """Build a Gmail users.settings.filters.create body.

    Args:
        rule: Unified sort rule.
        destination_label_id: Gmail label id to add (never SPAM/TRASH unless that is the id).

    Returns:
        Filter resource dict with criteria and skip-inbox action.
    """
    criteria: dict[str, str] = {"from": rule.match.from_value}
    if rule.match.subject_contains:
        criteria["subject"] = rule.match.subject_contains
    return {
        "criteria": criteria,
        "action": {
            "addLabelIds": [destination_label_id],
            "removeLabelIds": ["INBOX"],
        },
    }


def from_gmail_filter(
    filter_body: dict[str, Any],
    label_names: dict[str, str],
) -> MailRule | None:
    """Parse a Gmail filter into a MailRule if it skips Inbox.

    Args:
        filter_body: Filter resource from filters.list/get.
        label_names: Map of label id to display name.

    Returns:
        MailRule, or None if the filter does not skip Inbox or has no usable from.
    """
    action = filter_body.get("action") or {}
    if "INBOX" not in (action.get("removeLabelIds") or []):
        return None
    add_ids = action.get("addLabelIds") or []
    dest_id = add_ids[0] if add_ids else ""
    dest_name = label_names.get(dest_id, dest_id)
    criteria = filter_body.get("criteria") or {}
    from_value = str(criteria.get("from") or "")
    subject = criteria.get("subject")
    try:
        match = MailRuleMatch(
            from_value=from_value,
            subject_contains=str(subject) if subject else None,
        )
    except ValidationError:
        return None
    return MailRule(
        id=filter_body.get("id"),
        name=f"Sort: {match.from_value} → {dest_name}",
        enabled=True,
        match=match,
        destination=dest_name,
    )
