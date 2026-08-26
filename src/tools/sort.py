"""MCP handlers for durable mail sort rules on Gmail and Outlook."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..handler_context import HandlerContext
from ..sort.models import STARTER_FOLDERS, MailRule, MailRuleMatch
from .response import error_content as _error_content
from .response import text_content as _text_content


class CreateSortRuleInput(BaseModel):
    """Validated arguments for gmail_create_sort_rule."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    from_value: str = Field(alias="fromValue")
    destination: str
    subject_contains: str | None = Field(default=None, alias="subjectContains")
    apply_existing: bool = Field(default=True, alias="applyExisting")
    max_existing: int = Field(default=200, alias="maxExisting")

    @field_validator("from_value")
    @classmethod
    def validate_from_value(cls, value: str) -> str:
        """Reuse MailRuleMatch validation for the tool boundary."""
        return MailRuleMatch(from_value=value).from_value

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        """Reject blank destination names."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("destination is required")
        return stripped

    @field_validator("max_existing")
    @classmethod
    def validate_max_existing(cls, value: int) -> int:
        """Cap retroactive filing at 500 messages."""
        if value < 1 or value > 500:
            raise ValueError("maxExisting must be between 1 and 500")
        return value


def _validation_message(exc: ValidationError) -> str:
    err = exc.errors()[0]
    return str(err.get("msg", exc))


def handle_ensure_sort_folders(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """Create starter (and optional extra) folders/labels. Idempotent.

    Args:
        args: Optional extra folder names.
        ctx: Handler context with an EmailClient.

    Returns:
        MCP text listing folder ids and names.
    """
    extra = args.get("extra") or []
    names = list(STARTER_FOLDERS) + [str(n) for n in extra]
    folders = ctx.client.ensure_folders(names)
    lines = [f"Ensured {len(folders)} folders:"]
    for folder in folders:
        lines.append(f"  - {folder['name']} (id: {folder['id']})")
    return _text_content("\n".join(lines))


def handle_create_sort_rule(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """Create a native skip-inbox / move rule and optionally file existing mail.

    Args:
        args: CamelCase tool arguments.
        ctx: Handler context with an EmailClient.

    Returns:
        MCP text with rule id and existing_moved count, or an error.
    """
    try:
        parsed = CreateSortRuleInput.model_validate(args)
    except ValidationError as exc:
        return _error_content(_validation_message(exc))
    rule = MailRule(
        name=parsed.name,
        match=MailRuleMatch(
            from_value=parsed.from_value,
            subject_contains=parsed.subject_contains,
        ),
        destination=parsed.destination,
    )
    try:
        created = ctx.client.create_sort_rule(
            rule,
            apply_existing=parsed.apply_existing,
            max_existing=parsed.max_existing,
        )
    except RuntimeError as exc:
        return _error_content(str(exc))
    return _text_content(
        f"Created sort rule {created.id} ({created.name}).\n"
        f"Destination: {created.destination}\n"
        f"Existing moved: {created.existing_moved}\n"
        f"Existing failed: {created.existing_failed}"
    )


def handle_list_sort_rules(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """List native skip-inbox / move-to-folder rules.

    Args:
        args: Unused; account is resolved before the handler.
        ctx: Handler context with an EmailClient.

    Returns:
        MCP text, one rule per line.
    """
    del args
    try:
        rules = ctx.client.list_sort_rules()
    except RuntimeError as exc:
        return _error_content(str(exc))
    if not rules:
        return _text_content("No sort rules found.")
    lines = [f"Found {len(rules)} sort rules:"]
    for rule in rules:
        lines.append(
            f"  - {rule.id} | {rule.name} | from={rule.match.from_value} "
            f"| dest={rule.destination} | enabled={rule.enabled}"
        )
    return _text_content("\n".join(lines))


def handle_delete_sort_rule(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """Delete a native sort rule by provider id. Does not move mail.

    Args:
        args: Must include ruleId.
        ctx: Handler context with an EmailClient.

    Returns:
        MCP text confirming deletion, or an error.
    """
    rule_id = args.get("ruleId")
    if not rule_id:
        return _error_content("ruleId is required.")
    try:
        ctx.client.delete_sort_rule(str(rule_id))
    except RuntimeError as exc:
        return _error_content(str(exc))
    return _text_content(f"Deleted sort rule {rule_id}. Filed mail was left in place.")
