from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.sort.models import STARTER_FOLDERS, MailRule, MailRuleMatch


class TestStarterFolders:
    def test_six_named_folders_in_order(self) -> None:
        assert STARTER_FOLDERS == (
            "Newsletters",
            "Receipts",
            "Finance",
            "Travel",
            "Social",
            "Junk",
        )


class TestMailRuleMatch:
    def test_accepts_email_address(self) -> None:
        match = MailRuleMatch(from_value="News@Example.com")
        assert match.from_value == "news@example.com"

    def test_accepts_domain(self) -> None:
        match = MailRuleMatch(from_value="Example.COM")
        assert match.from_value == "example.com"

    def test_strips_whitespace(self) -> None:
        match = MailRuleMatch(from_value="  bills@bank.com  ")
        assert match.from_value == "bills@bank.com"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValidationError, match="email address or a domain"):
            MailRuleMatch(from_value="")

    def test_rejects_wildcard(self) -> None:
        with pytest.raises(ValidationError, match="email address or a domain"):
            MailRuleMatch(from_value="*.example.com")

    def test_rejects_no_dot(self) -> None:
        with pytest.raises(ValidationError, match="email address or a domain"):
            MailRuleMatch(from_value="localhost")


class TestMailRule:
    def test_defaults(self) -> None:
        rule = MailRule(
            name="Newsletters from shop",
            match=MailRuleMatch(from_value="shop.com"),
            destination="Newsletters",
        )
        assert rule.enabled is True
        assert rule.id is None
        assert rule.existing_moved == 0
        assert rule.existing_failed == 0
