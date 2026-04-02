from __future__ import annotations

from src.outlook_query import translate_gmail_query


class TestTranslateGmailQuery:
    def test_from_operator(self) -> None:
        result = translate_gmail_query("from:user@example.com")
        assert result.search == "from:user@example.com"

    def test_subject_operator(self) -> None:
        result = translate_gmail_query("subject:meeting")
        assert result.search == "subject:meeting"

    def test_is_unread(self) -> None:
        result = translate_gmail_query("is:unread")
        assert "isRead eq false" in result.filter

    def test_is_important(self) -> None:
        result = translate_gmail_query("is:important")
        assert "importance eq 'high'" in result.filter

    def test_is_starred(self) -> None:
        result = translate_gmail_query("is:starred")
        assert "flagStatus eq 'flagged'" in result.filter

    def test_has_attachment(self) -> None:
        result = translate_gmail_query("has:attachment")
        assert "hasAttachments eq true" in result.filter

    def test_after_date(self) -> None:
        result = translate_gmail_query("after:2024/1/15")
        assert "receivedDateTime ge 2024-01-15" in result.filter

    def test_before_date(self) -> None:
        result = translate_gmail_query("before:2024/12/31")
        assert "receivedDateTime lt 2024-12-31" in result.filter

    def test_in_inbox(self) -> None:
        result = translate_gmail_query("in:inbox")
        assert result.folder == "inbox"

    def test_in_sent(self) -> None:
        result = translate_gmail_query("in:sent")
        assert result.folder == "sentitems"

    def test_in_drafts(self) -> None:
        result = translate_gmail_query("in:drafts")
        assert result.folder == "drafts"

    def test_in_trash(self) -> None:
        result = translate_gmail_query("in:trash")
        assert result.folder == "deleteditems"

    def test_label_becomes_category(self) -> None:
        result = translate_gmail_query("label:Travel")
        assert "categories/any" in result.filter
        assert "Travel" in result.filter

    def test_newer_than_days(self) -> None:
        result = translate_gmail_query("newer_than:7d")
        assert "receivedDateTime ge" in result.filter

    def test_mixed_search_and_filter(self) -> None:
        result = translate_gmail_query("from:boss@company.com is:unread has:attachment")
        assert result.search == "from:boss@company.com"
        assert "isRead eq false" in result.filter
        assert "hasAttachments eq true" in result.filter

    def test_exact_phrase(self) -> None:
        result = translate_gmail_query('"exact phrase"')
        assert '"exact phrase"' in result.search

    def test_negation(self) -> None:
        result = translate_gmail_query("-from:noreply@example.com")
        assert "NOT from:noreply@example.com" in result.search

    def test_or_operator(self) -> None:
        result = translate_gmail_query("from:alice OR from:bob")
        assert "from:alice OR from:bob" in result.search

    def test_plain_text_search(self) -> None:
        result = translate_gmail_query("hello world")
        assert result.search == "hello world"
        assert result.filter == ""
        assert result.folder is None

    def test_empty_query(self) -> None:
        result = translate_gmail_query(None)
        assert result.search == ""
        assert result.filter == ""
        assert result.folder is None
