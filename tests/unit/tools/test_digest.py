"""Unit tests for handle_generate_digest tool handler."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from src.handler_context import HandlerContext
from src.triage.cache import TriageCache


def _make_cache() -> TriageCache:
    cache = TriageCache(Path(":memory:"))
    cache.initialize()
    return cache


def _ctx(client: Any = None, cache: Any = None) -> HandlerContext:
    return HandlerContext(client=client or MagicMock(), cache=cache or _make_cache())


def _make_client(email: str = "test@gmail.com") -> MagicMock:
    client = MagicMock()
    client.email_address = email
    client.search_messages.return_value = {"messages": []}
    return client


class TestHandleGenerateDigest:
    def test_basic_digest_generation(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({}, _ctx(client))

        assert not result.get("isError")
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert data["account"] == "test@gmail.com"
        assert data["period"] == "daily"

    def test_returns_structured_json_in_content(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({}, _ctx(client))

        assert "content" in result
        assert result["content"][0]["type"] == "text"
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert "summary" in data
        assert "actionable" in data
        assert "generated_at" in data

    def test_send_email_false_does_not_call_send(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        handle_generate_digest({"sendEmail": False}, _ctx(client))

        client.send_email.assert_not_called()

    def test_send_email_true_calls_send_email(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({"sendEmail": True}, _ctx(client))

        assert not result.get("isError")
        client.send_email.assert_called_once()

    def test_send_email_true_sends_to_own_address(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client(email="test@gmail.com")
        handle_generate_digest({"sendEmail": True}, _ctx(client))

        call_kwargs = client.send_email.call_args
        to_addr = call_kwargs.kwargs.get("to") or call_kwargs.args[0]
        assert to_addr == "test@gmail.com"

    def test_send_email_true_sets_sent_flag(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({"sendEmail": True}, _ctx(client))

        data = json.loads(result["content"][0]["text"])
        assert data["sent"] is True

    def test_send_email_false_sent_flag_is_false(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({"sendEmail": False}, _ctx(client))

        data = json.loads(result["content"][0]["text"])
        assert data["sent"] is False

    def test_invalid_period_returns_error(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({"period": "monthly"}, _ctx(client))

        assert result["isError"] is True
        assert "monthly" in result["content"][0]["text"]

    def test_period_weekly_accepted(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({"period": "weekly"}, _ctx(client))

        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert data["period"] == "weekly"

    def test_default_period_is_daily(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        result = handle_generate_digest({}, _ctx(client))

        data = json.loads(result["content"][0]["text"])
        assert data["period"] == "daily"

    def test_error_handling_wraps_exceptions(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        client.search_messages.side_effect = RuntimeError("API failure")
        result = handle_generate_digest({}, _ctx(client))

        assert result["isError"] is True
        assert "API failure" in result["content"][0]["text"]

    def test_no_cache_context_still_generates(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        ctx = HandlerContext(client=client, cache=_make_cache(), calendar_ctx=None)
        result = handle_generate_digest({}, ctx)

        assert not result.get("isError")

    def test_max_results_passed_through(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        handle_generate_digest({"maxResults": 50}, _ctx(client))

        client.search_messages.assert_called_once_with(q="is:unread", max_results=50)

    def test_send_email_uses_html_content_type(self) -> None:
        from src.tools.digest import handle_generate_digest

        client = _make_client()
        handle_generate_digest({"sendEmail": True}, _ctx(client))

        call_kwargs = client.send_email.call_args
        content_type = call_kwargs.kwargs.get("content_type")
        assert content_type == "text/html"
