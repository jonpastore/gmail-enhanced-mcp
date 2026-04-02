"""Itinerary extraction tool handler."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..handler_context import HandlerContext
from ..itinerary_parser import ItineraryParser
from .response import error_content as _error_content
from .response import text_content as _text_content


def handle_extract_itinerary(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """Extract travel itinerary segments from inbox messages.

    Searches for confirmation and booking emails within the given date window,
    parses them with ItineraryParser, and returns a structured JSON itinerary.

    Args:
        args: Tool arguments with optional dateFrom, dateTo, and maxResults.
        ctx: Handler context with client for searching and reading messages.

    Returns:
        MCP content with the parsed Itinerary as JSON.
    """
    import json

    today = date.today()
    default_to = today + timedelta(days=30)

    date_from_str: str = args.get("dateFrom", today.isoformat())
    date_to_str: str = args.get("dateTo", default_to.isoformat())
    max_results: int = args.get("maxResults", 50)

    try:
        date_from = date.fromisoformat(date_from_str)
        date_to = date.fromisoformat(date_to_str)
    except ValueError as exc:
        return _error_content(f"Invalid date format (expected YYYY-MM-DD): {exc}")

    if date_from >= date_to:
        return _error_content(f"dateFrom ({date_from_str}) must be before dateTo ({date_to_str})")

    after = date_from.strftime("%Y/%m/%d")
    before = date_to.strftime("%Y/%m/%d")
    query = (
        f"(confirmation OR itinerary OR booking OR reservation OR e-ticket)"
        f" after:{after} before:{before}"
    )

    try:
        result = ctx.client.search_messages(q=query, max_results=max_results)
    except Exception as exc:
        return _error_content(f"Search failed: {exc}")

    stubs: list[dict[str, Any]] = result.get("messages", [])
    if not stubs:
        return _text_content(
            f"No travel-related messages found between {date_from_str} and {date_to_str}."
        )

    messages: list[dict[str, Any]] = []
    for stub in stubs:
        try:
            msg = ctx.client.read_message(stub["id"])
            messages.append(msg)
        except Exception:
            continue

    parser = ItineraryParser()
    itinerary = parser.parse_messages(messages)

    return _text_content(json.dumps(itinerary.model_dump(), indent=2))
