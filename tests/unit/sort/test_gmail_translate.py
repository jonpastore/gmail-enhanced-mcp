from __future__ import annotations

from src.sort.gmail_translate import from_gmail_filter, to_gmail_filter
from src.sort.models import MailRule, MailRuleMatch


def _rule(from_value: str = "shop.com", destination: str = "Newsletters") -> MailRule:
    return MailRule(
        name="Shop news",
        match=MailRuleMatch(from_value=from_value),
        destination=destination,
    )


class TestToGmailFilter:
    def test_from_and_skip_inbox(self) -> None:
        body = to_gmail_filter(_rule(), destination_label_id="Label_news")
        assert body["criteria"]["from"] == "shop.com"
        assert body["action"]["addLabelIds"] == ["Label_news"]
        assert body["action"]["removeLabelIds"] == ["INBOX"]

    def test_junk_destination_uses_provided_label_not_spam(self) -> None:
        body = to_gmail_filter(_rule(destination="Junk"), destination_label_id="Label_junk")
        assert body["action"]["addLabelIds"] == ["Label_junk"]
        assert "SPAM" not in body["action"]["addLabelIds"]
        assert "TRASH" not in body["action"]["addLabelIds"]

    def test_includes_subject_when_set(self) -> None:
        rule = _rule()
        rule.match.subject_contains = "invoice"
        body = to_gmail_filter(rule, destination_label_id="Label_fin")
        assert body["criteria"]["subject"] == "invoice"

    def test_omits_subject_when_unset(self) -> None:
        body = to_gmail_filter(_rule(), destination_label_id="Label_news")
        assert "subject" not in body["criteria"]
        assert "query" not in body["criteria"]


class TestFromGmailFilter:
    def test_skip_inbox_filter_becomes_rule(self) -> None:
        raw = {
            "id": "f1",
            "criteria": {"from": "shop.com"},
            "action": {"addLabelIds": ["Label_news"], "removeLabelIds": ["INBOX"]},
        }
        rule = from_gmail_filter(raw, {"Label_news": "Newsletters"})
        assert rule is not None
        assert rule.id == "f1"
        assert rule.match.from_value == "shop.com"
        assert rule.destination == "Newsletters"
        assert rule.name == "Sort: shop.com → Newsletters"

    def test_non_skip_inbox_returns_none(self) -> None:
        raw = {
            "id": "f2",
            "criteria": {"from": "shop.com"},
            "action": {"addLabelIds": ["Label_news"], "removeLabelIds": []},
        }
        assert from_gmail_filter(raw, {"Label_news": "Newsletters"}) is None

    def test_trash_block_filter_maps_destination_trash(self) -> None:
        raw = {
            "id": "f3",
            "criteria": {"from": "spam@example.com"},
            "action": {"addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]},
        }
        rule = from_gmail_filter(raw, {})
        assert rule is not None
        assert rule.destination == "TRASH"
        assert rule.name == "Sort: spam@example.com → TRASH"
