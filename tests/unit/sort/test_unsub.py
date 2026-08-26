from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.sort.unsub import execute_one_click, parse_mailto, parse_unsubscribe_headers


class TestParseUnsubscribeHeaders:
    def test_https_and_one_click(self) -> None:
        result = parse_unsubscribe_headers(
            [
                {"name": "List-Unsubscribe", "value": "<https://example.com/unsub>"},
                {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"},
            ]
        )
        assert result["found"] is True
        assert result["unsubscribe_url"] == "https://example.com/unsub"
        assert result["one_click"] is True

    def test_mailto_only(self) -> None:
        result = parse_unsubscribe_headers(
            [{"name": "List-Unsubscribe", "value": "<mailto:unsub@example.com?subject=unsub>"}]
        )
        assert result["unsubscribe_mailto"] == "mailto:unsub@example.com?subject=unsub"
        assert result["one_click"] is False

    def test_missing_returns_not_found(self) -> None:
        result = parse_unsubscribe_headers([{"name": "Subject", "value": "Hi"}])
        assert result["found"] is False


class TestParseMailto:
    def test_address_and_subject(self) -> None:
        to, subject = parse_mailto("mailto:unsub@example.com?subject=unsub")
        assert to == "unsub@example.com"
        assert subject == "unsub"

    def test_address_only(self) -> None:
        to, subject = parse_mailto("mailto:unsub@example.com")
        assert to == "unsub@example.com"
        assert subject == "unsubscribe"


class TestExecuteOneClick:
    @patch("src.sort.unsub.requests")
    def test_posts_rfc8058_body(self, mock_requests: MagicMock) -> None:
        mock_requests.post.return_value = MagicMock(status_code=200)
        result = execute_one_click("https://example.com/unsub")
        assert result["method"] == "one_click"
        kwargs = mock_requests.post.call_args.kwargs
        assert kwargs["data"] == "List-Unsubscribe=One-Click"
        assert kwargs["allow_redirects"] is False

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            execute_one_click("http://example.com/unsub")
