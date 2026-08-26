from __future__ import annotations

from src.sort.errors import (
    gmail_sort_http_error,
    inbox_search_query,
    outlook_sort_http_error,
)
from src.sort.gmail_translate import from_gmail_filter
from src.sort.outlook_translate import from_outlook_rule


class TestInboxSearchQuery:
    def test_includes_subject(self) -> None:
        q = inbox_search_query("shop.com", "invoice")
        assert q == "from:shop.com in:inbox subject:invoice"


class TestHttpMapping:
    def test_gmail_non_403_is_generic(self) -> None:
        exc = Exception("boom")
        err = gmail_sort_http_error(exc, "create")
        assert str(err) == "Failed to create sort rule"

    def test_outlook_non_403_is_generic(self) -> None:
        exc = Exception("boom")
        err = outlook_sort_http_error(exc, "list")
        assert str(err) == "Failed to list sort rule"


class TestReverseTranslateGaps:
    def test_gmail_invalid_from_returns_none(self) -> None:
        raw = {
            "id": "f1",
            "criteria": {"from": "nodot"},
            "action": {"addLabelIds": ["L1"], "removeLabelIds": ["INBOX"]},
        }
        assert from_gmail_filter(raw, {}) is None

    def test_outlook_subject_and_missing_from_returns_none(self) -> None:
        raw = {
            "id": "r1",
            "displayName": "x",
            "conditions": {"subjectContains": ["hello"]},
            "actions": {"moveToFolder": "fld"},
        }
        assert from_outlook_rule(raw, {"fld": "Newsletters"}) is None
