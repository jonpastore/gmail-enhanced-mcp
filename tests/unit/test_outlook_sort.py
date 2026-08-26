from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.outlook_client import OutlookClient
from src.sort.models import MailRule, MailRuleMatch


def _make_client() -> OutlookClient:
    token_mgr = MagicMock()
    token_mgr.get_token.return_value = "fake-token"
    return OutlookClient(token_mgr, "test@outlook.com")


def _rule() -> MailRule:
    return MailRule(
        name="Shop news",
        match=MailRuleMatch(from_value="news@shop.com"),
        destination="Newsletters",
    )


def _json_resp(payload: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


class TestCreateLabelCreatesFolder:
    @patch("src.outlook_client.requests")
    def test_posts_mail_folders(self, mock_requests: MagicMock) -> None:
        mock_requests.post.return_value = _json_resp({"id": "fld1", "displayName": "Junk"})
        client = _make_client()
        result = client.create_label("Junk")
        assert result == {"id": "fld1", "name": "Junk"}
        path = mock_requests.post.call_args.args[0]
        assert path.endswith("/me/mailFolders")


class TestEnsureFolders:
    @patch("src.outlook_client.requests")
    def test_creates_missing_folder(self, mock_requests: MagicMock) -> None:
        mock_requests.get.return_value = _json_resp(
            {"value": [{"id": "n1", "displayName": "Newsletters"}]}
        )
        mock_requests.post.return_value = _json_resp({"id": "j1", "displayName": "Junk"})
        client = _make_client()
        result = client.ensure_folders(["Newsletters", "Junk"])
        assert result[0] == {"id": "n1", "name": "Newsletters"}
        assert result[1] == {"id": "j1", "name": "Junk"}


class TestMoveMessages:
    @patch("src.outlook_client.requests")
    def test_posts_move_per_message(self, mock_requests: MagicMock) -> None:
        mock_requests.post.return_value = _json_resp({"id": "m1"})
        client = _make_client()
        result = client.move_messages(["m1", "m2"], "fld-news")
        assert result["moved"] == 2
        assert result["failed"] == 0
        assert mock_requests.post.call_count == 2
        assert "/me/messages/m1/move" in mock_requests.post.call_args_list[0].args[0]


class TestCreateSortRule:
    @patch("src.outlook_client.requests")
    def test_creates_message_rule(self, mock_requests: MagicMock) -> None:
        def _get(url: str, **kwargs: object) -> MagicMock:
            if url.endswith("/me/mailFolders"):
                return _json_resp({"value": [{"id": "fld-news", "displayName": "Newsletters"}]})
            if url.endswith("/messageRules"):
                return _json_resp({"value": []})
            if "/mailFolders/inbox/messages" in url or url.endswith("/messages"):
                return _json_resp({"value": []})
            return _json_resp({"value": []})

        mock_requests.get.side_effect = _get
        mock_requests.post.return_value = _json_resp({"id": "rule-1", "displayName": "Shop news"})
        client = _make_client()
        result = client.create_sort_rule(_rule(), apply_existing=False)
        assert result.id == "rule-1"
        posted = mock_requests.post.call_args
        assert posted.kwargs["json"]["actions"]["moveToFolder"] == "fld-news"
        assert posted.kwargs["json"]["actions"]["stopProcessingRules"] is False

    @patch("src.outlook_client.requests")
    def test_403_names_mailbox_settings_scope(self, mock_requests: MagicMock) -> None:
        mock_requests.get.return_value = _json_resp(
            {"value": [{"id": "fld-news", "displayName": "Newsletters"}]}
        )
        err = requests.HTTPError("Forbidden")
        err.response = MagicMock(status_code=403)
        forbidden = MagicMock()
        forbidden.raise_for_status.side_effect = err
        mock_requests.post.return_value = forbidden
        client = _make_client()
        with pytest.raises(RuntimeError, match="MailboxSettings.ReadWrite"):
            client.create_sort_rule(_rule(), apply_existing=False)


class TestDeleteSortRule:
    @patch("src.outlook_client.requests")
    def test_read_only_rule_actionable_error(self, mock_requests: MagicMock) -> None:
        mock_requests.get.return_value = _json_resp(
            {"id": "r1", "isReadOnly": True, "displayName": "System"}
        )
        client = _make_client()
        with pytest.raises(RuntimeError, match="read-only"):
            client.delete_sort_rule("r1")
        mock_requests.delete.assert_not_called()
