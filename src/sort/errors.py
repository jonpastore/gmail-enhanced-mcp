"""Actionable errors for sort-rule provider calls. No PII."""

from __future__ import annotations

from typing import Any

GMAIL_FILTER_SCOPE_MSG = (
    "Missing OAuth scope(s): gmail.settings.basic. Run: python -m gmail_mcp auth"
)
OUTLOOK_RULE_SCOPE_MSG = (
    "Missing OAuth scope(s): MailboxSettings.ReadWrite. "
    "Re-auth after adding the Azure delegated permission."
)
OUTLOOK_READONLY_MSG = "This Outlook rule is read-only and cannot be deleted via the API."


def gmail_sort_http_error(exc: BaseException, action: str) -> RuntimeError:
    """Map a Gmail HttpError to a user-facing RuntimeError.

    Args:
        exc: Raised Google API error.
        action: create, list, or delete.

    Returns:
        RuntimeError with a scope hint on 403, generic message otherwise.
    """
    status = _http_status(exc)
    if status == 403:
        return RuntimeError(GMAIL_FILTER_SCOPE_MSG)
    return RuntimeError(f"Failed to {action} sort rule")


def outlook_sort_http_error(exc: BaseException, action: str) -> RuntimeError:
    """Map a Graph HTTPError to a user-facing RuntimeError.

    Args:
        exc: Raised requests HTTPError.
        action: create, list, or delete.

    Returns:
        RuntimeError with a scope hint on 403, generic message otherwise.
    """
    status = _http_status(exc)
    if status == 403:
        return RuntimeError(OUTLOOK_RULE_SCOPE_MSG)
    return RuntimeError(f"Failed to {action} sort rule")


def inbox_search_query(from_value: str, subject_contains: str | None) -> str:
    """Gmail-syntax query for Inbox matches of a sort rule.

    Args:
        from_value: Email or domain.
        subject_contains: Optional subject substring.

    Returns:
        Query string for search_messages.
    """
    query = f"from:{from_value} in:inbox"
    if subject_contains:
        query += f" subject:{subject_contains}"
    return query


def _http_status(exc: BaseException) -> int:
    resp: Any = getattr(exc, "response", None)
    if resp is None:
        resp = getattr(exc, "resp", None)
    if resp is None:
        return 0
    for attr in ("status_code", "status"):
        value = getattr(resp, attr, None)
        if isinstance(value, int):
            return value
    return 0
