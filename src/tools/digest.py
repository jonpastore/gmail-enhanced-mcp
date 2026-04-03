from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..digest.engine import DigestEngine
from ..digest.formatter import format_digest_html
from ..handler_context import HandlerContext
from .response import error_content as _error_content
from .response import text_content as _text_content


def handle_generate_digest(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    """Generate a structured email digest for an account.

    Args:
        args: Tool arguments with optional period, sendEmail, maxResults.
        ctx: Handler context with client, cache, calendar_ctx.

    Returns:
        MCP content with digest data.
    """
    try:
        period = args.get("period", "daily")
        send_email = args.get("sendEmail", False)
        max_results = args.get("maxResults", 100)

        if period not in ("daily", "weekly"):
            return _error_content(f"Invalid period '{period}'. Must be 'daily' or 'weekly'.")

        engine = DigestEngine(ctx.client, ctx.cache, ctx.calendar_ctx)
        result = engine.generate(period=period, max_results=max_results)

        if send_email:
            html = format_digest_html(result)
            date_str = datetime.now(UTC).strftime("%b %d, %Y")
            subject = f"[Digest] {period.title()} Email Summary \u2014 {date_str}"
            ctx.client.send_email(
                to=ctx.client.email_address,
                subject=subject,
                body=html,
                content_type="text/html",
            )
            result.sent = True

        return _text_content(result.model_dump_json(indent=2))
    except Exception as exc:
        return _error_content(str(exc))
