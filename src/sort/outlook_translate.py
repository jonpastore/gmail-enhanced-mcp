"""Compile MailRule to Microsoft Graph messageRule JSON and back. No API calls."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .models import MailRule, MailRuleMatch


def to_outlook_rule(
    rule: MailRule,
    destination_folder_id: str,
    sequence: int,
) -> dict[str, Any]:
    """Build a Graph inbox messageRule create body.

    Args:
        rule: Unified sort rule.
        destination_folder_id: Graph mailFolder id to move into.
        sequence: Rule sequence (max existing + 1).

    Returns:
        messageRule JSON for POST /me/mailFolders/inbox/messageRules.
    """
    conditions: dict[str, Any] = {}
    if "@" in rule.match.from_value:
        conditions["fromAddresses"] = [{"emailAddress": {"address": rule.match.from_value}}]
    else:
        conditions["senderContains"] = [rule.match.from_value]
    if rule.match.subject_contains:
        conditions["subjectContains"] = [rule.match.subject_contains]
    return {
        "displayName": rule.name,
        "sequence": sequence,
        "isEnabled": rule.enabled,
        "conditions": conditions,
        "actions": {
            "moveToFolder": destination_folder_id,
            "stopProcessingRules": False,
        },
    }


def from_outlook_rule(
    rule_body: dict[str, Any],
    folder_names: dict[str, str],
) -> MailRule | None:
    """Parse a Graph messageRule into a MailRule if it moves to a folder.

    Args:
        rule_body: messageRule resource.
        folder_names: Map of folder id to display name.

    Returns:
        MailRule, or None if the rule does not move to a folder.
    """
    actions = rule_body.get("actions") or {}
    dest_id = actions.get("moveToFolder")
    if not dest_id:
        return None
    dest_name = folder_names.get(dest_id, dest_id)
    conditions = rule_body.get("conditions") or {}
    from_value = _extract_from_value(conditions)
    if from_value is None:
        return None
    subjects = conditions.get("subjectContains") or []
    subject = subjects[0] if subjects else None
    try:
        match = MailRuleMatch(from_value=from_value, subject_contains=subject)
    except ValidationError:
        return None
    return MailRule(
        id=rule_body.get("id"),
        name=str(rule_body.get("displayName") or match.from_value),
        enabled=bool(rule_body.get("isEnabled", True)),
        match=match,
        destination=dest_name,
    )


def _extract_from_value(conditions: dict[str, Any]) -> str | None:
    addresses = conditions.get("fromAddresses") or []
    if addresses:
        addr = addresses[0].get("emailAddress", {}).get("address")
        if addr:
            return str(addr)
    contains = conditions.get("senderContains") or []
    if contains:
        return str(contains[0])
    return None
