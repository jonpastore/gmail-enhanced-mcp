from __future__ import annotations

from unittest.mock import MagicMock

from src.handler_context import HandlerContext
from src.sort.models import STARTER_FOLDERS, MailRule, MailRuleMatch
from src.tools.sort import (
    handle_create_sort_rule,
    handle_delete_sort_rule,
    handle_ensure_sort_folders,
    handle_list_sort_rules,
)


def _ctx(provider: str = "gmail") -> HandlerContext:
    client = MagicMock()
    client.provider = provider
    client.email_address = "user@example.com"
    return HandlerContext(client=client)


class TestEnsureSortFolders:
    def test_creates_starter_folders(self) -> None:
        ctx = _ctx()
        ctx.client.ensure_folders.return_value = [
            {"id": "1", "name": name} for name in STARTER_FOLDERS
        ]
        result = handle_ensure_sort_folders({}, ctx)
        ctx.client.ensure_folders.assert_called_once_with(list(STARTER_FOLDERS))
        text = result["content"][0]["text"]
        assert "Newsletters" in text
        assert "Junk" in text

    def test_appends_extra_names(self) -> None:
        ctx = _ctx("outlook")
        ctx.client.ensure_folders.return_value = []
        handle_ensure_sort_folders({"extra": ["Vendors"]}, ctx)
        names = ctx.client.ensure_folders.call_args.args[0]
        assert names[-1] == "Vendors"
        assert "Newsletters" in names


class TestCreateSortRule:
    def test_creates_on_outlook(self) -> None:
        ctx = _ctx("outlook")
        ctx.client.create_sort_rule.return_value = MailRule(
            id="r1",
            name="Shop",
            match=MailRuleMatch(from_value="shop.com"),
            destination="Newsletters",
            existing_moved=4,
            existing_failed=0,
        )
        result = handle_create_sort_rule(
            {"name": "Shop", "fromValue": "shop.com", "destination": "Newsletters"},
            ctx,
        )
        assert "only available for Gmail" not in result["content"][0]["text"]
        assert "r1" in result["content"][0]["text"]
        assert "4" in result["content"][0]["text"]
        kwargs = ctx.client.create_sort_rule.call_args.kwargs
        assert kwargs["apply_existing"] is True

    def test_rejects_max_existing_over_500(self) -> None:
        result = handle_create_sort_rule(
            {
                "name": "Shop",
                "fromValue": "shop.com",
                "destination": "Newsletters",
                "maxExisting": 501,
            },
            _ctx(),
        )
        assert result.get("isError") is True
        assert "1 and 500" in result["content"][0]["text"]

    def test_rejects_invalid_from_value(self) -> None:
        result = handle_create_sort_rule(
            {"name": "Shop", "fromValue": "nodot", "destination": "Newsletters"},
            _ctx(),
        )
        assert result.get("isError") is True
        assert "email address or a domain" in result["content"][0]["text"]

    def test_apply_existing_false_passed_through(self) -> None:
        ctx = _ctx()
        ctx.client.create_sort_rule.return_value = MailRule(
            id="r1",
            name="Shop",
            match=MailRuleMatch(from_value="shop.com"),
            destination="Newsletters",
        )
        handle_create_sort_rule(
            {
                "name": "Shop",
                "fromValue": "shop.com",
                "destination": "Newsletters",
                "applyExisting": False,
            },
            ctx,
        )
        assert ctx.client.create_sort_rule.call_args.kwargs["apply_existing"] is False


class TestListSortRules:
    def test_lists_rules(self) -> None:
        ctx = _ctx()
        ctx.client.list_sort_rules.return_value = [
            MailRule(
                id="f1",
                name="Sort: shop.com → Newsletters",
                match=MailRuleMatch(from_value="shop.com"),
                destination="Newsletters",
            )
        ]
        result = handle_list_sort_rules({}, ctx)
        text = result["content"][0]["text"]
        assert "f1" in text
        assert "Newsletters" in text


class TestDeleteSortRule:
    def test_deletes_by_id(self) -> None:
        ctx = _ctx()
        result = handle_delete_sort_rule({"ruleId": "f1"}, ctx)
        ctx.client.delete_sort_rule.assert_called_once_with("f1")
        assert "Deleted" in result["content"][0]["text"]

    def test_requires_rule_id(self) -> None:
        result = handle_delete_sort_rule({}, _ctx())
        assert result.get("isError") is True
