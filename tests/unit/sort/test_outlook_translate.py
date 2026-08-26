from __future__ import annotations

from src.sort.models import MailRule, MailRuleMatch
from src.sort.outlook_translate import from_outlook_rule, to_outlook_rule


def _rule(from_value: str = "news@shop.com", destination: str = "Newsletters") -> MailRule:
    return MailRule(
        name="Shop news",
        match=MailRuleMatch(from_value=from_value),
        destination=destination,
    )


class TestToOutlookRule:
    def test_email_uses_from_addresses(self) -> None:
        body = to_outlook_rule(_rule(), destination_folder_id="folder-news", sequence=3)
        assert body["displayName"] == "Shop news"
        assert body["sequence"] == 3
        assert body["isEnabled"] is True
        assert body["conditions"]["fromAddresses"][0]["emailAddress"]["address"] == "news@shop.com"
        assert "senderContains" not in body["conditions"]
        assert body["actions"]["moveToFolder"] == "folder-news"
        assert body["actions"]["stopProcessingRules"] is False

    def test_domain_uses_sender_contains(self) -> None:
        body = to_outlook_rule(_rule(from_value="shop.com"), "folder-news", sequence=1)
        assert body["conditions"]["senderContains"] == ["shop.com"]
        assert "fromAddresses" not in body["conditions"]

    def test_subject_contains_when_set(self) -> None:
        rule = _rule()
        rule.match.subject_contains = "invoice"
        body = to_outlook_rule(rule, "folder-fin", sequence=1)
        assert body["conditions"]["subjectContains"] == ["invoice"]


class TestFromOutlookRule:
    def test_move_rule_becomes_mail_rule(self) -> None:
        raw = {
            "id": "r1",
            "displayName": "Shop news",
            "isEnabled": True,
            "conditions": {
                "fromAddresses": [{"emailAddress": {"address": "news@shop.com"}}],
            },
            "actions": {"moveToFolder": "folder-news"},
        }
        rule = from_outlook_rule(raw, {"folder-news": "Newsletters"})
        assert rule is not None
        assert rule.id == "r1"
        assert rule.name == "Shop news"
        assert rule.match.from_value == "news@shop.com"
        assert rule.destination == "Newsletters"

    def test_non_move_rule_returns_none(self) -> None:
        raw = {
            "id": "r2",
            "displayName": "Delete spam",
            "conditions": {"subjectContains": ["win"]},
            "actions": {"delete": True},
        }
        assert from_outlook_rule(raw, {}) is None

    def test_sender_contains_domain(self) -> None:
        raw = {
            "id": "r3",
            "displayName": "Domain",
            "isEnabled": True,
            "conditions": {"senderContains": ["shop.com"]},
            "actions": {"moveToFolder": "folder-news"},
        }
        rule = from_outlook_rule(raw, {"folder-news": "Newsletters"})
        assert rule is not None
        assert rule.match.from_value == "shop.com"
