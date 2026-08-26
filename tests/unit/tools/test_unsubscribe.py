from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.handler_context import HandlerContext
from src.sort.models import MailRule, MailRuleMatch
from src.tools.hygiene import handle_get_unsubscribe_link
from src.tools.unsubscribe import handle_unsubscribe


def _ctx(provider: str = "gmail") -> HandlerContext:
    client = MagicMock()
    client.provider = provider
    client.email_address = "user@example.com"
    return HandlerContext(client=client)


class TestGetUnsubscribeOutlook:
    def test_works_on_outlook(self) -> None:
        ctx = _ctx("outlook")
        ctx.client.extract_unsubscribe_link.return_value = {
            "found": True,
            "unsubscribe_url": "https://example.com/unsub",
            "unsubscribe_mailto": None,
            "one_click": True,
        }
        result = handle_get_unsubscribe_link({"messageId": "m1"}, ctx)
        assert "only available for Gmail" not in result["content"][0]["text"]
        assert "https://example.com/unsub" in result["content"][0]["text"]


class TestHandleUnsubscribe:
    def test_requires_message_id(self) -> None:
        result = handle_unsubscribe({}, _ctx())
        assert result.get("isError") is True

    def test_one_click_does_not_send_mail(self) -> None:
        ctx = _ctx("outlook")
        ctx.client.extract_unsubscribe_link.return_value = {
            "found": True,
            "unsubscribe_url": "https://example.com/unsub",
            "unsubscribe_mailto": None,
            "one_click": True,
        }
        with patch("src.tools.unsubscribe.execute_one_click") as mock_exec:
            mock_exec.return_value = {"method": "one_click", "status": 200}
            result = handle_unsubscribe({"messageId": "m1"}, ctx)
        assert "one-click" in result["content"][0]["text"]
        ctx.client.send_email.assert_not_called()

    def test_mailto_sends_unsubscribe_mail(self) -> None:
        ctx = _ctx()
        ctx.client.extract_unsubscribe_link.return_value = {
            "found": True,
            "unsubscribe_url": None,
            "unsubscribe_mailto": "mailto:unsub@example.com?subject=leave",
            "one_click": False,
        }
        result = handle_unsubscribe({"messageId": "m1"}, ctx)
        assert "mailto" in result["content"][0]["text"]
        ctx.client.send_email.assert_called_once()
        kwargs = ctx.client.send_email.call_args.kwargs
        assert kwargs["to"] == "unsub@example.com"
        assert kwargs["subject"] == "leave"

    def test_non_one_click_url_refuses_get(self) -> None:
        ctx = _ctx()
        ctx.client.extract_unsubscribe_link.return_value = {
            "found": True,
            "unsubscribe_url": "https://example.com/unsub",
            "unsubscribe_mailto": None,
            "one_click": False,
        }
        result = handle_unsubscribe({"messageId": "m1"}, ctx)
        assert result.get("isError") is True
        assert "refusing to GET" in result["content"][0]["text"]
        ctx.client.send_email.assert_not_called()

    def test_create_junk_rule_from_sender(self) -> None:
        ctx = _ctx()
        ctx.client.extract_unsubscribe_link.return_value = {
            "found": True,
            "unsubscribe_url": "https://example.com/unsub",
            "unsubscribe_mailto": None,
            "one_click": True,
        }
        ctx.client.read_message.return_value = {
            "payload": {"headers": [{"name": "From", "value": "Shop <news@shop.com>"}]}
        }
        created = MailRule(
            id="r-junk",
            name="Junk news@shop.com",
            match=MailRuleMatch(from_value="news@shop.com"),
            destination="Junk",
        )
        ctx.client.create_sort_rule.return_value = created
        with patch("src.tools.unsubscribe.execute_one_click"):
            result = handle_unsubscribe({"messageId": "m1", "createJunkRule": True}, ctx)
        assert "r-junk" in result["content"][0]["text"]
        rule = ctx.client.create_sort_rule.call_args.args[0]
        assert rule.destination == "Junk"
        assert rule.match.from_value == "news@shop.com"
