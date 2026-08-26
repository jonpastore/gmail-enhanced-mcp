from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from src.gmail_client import GmailClient
from src.sort.models import MailRule, MailRuleMatch


def _make_client(mock_service: MagicMock | None = None) -> GmailClient:
    client = GmailClient.__new__(GmailClient)
    client._service = mock_service or MagicMock()
    client._account_email = "test@gmail.com"
    return client


def _rule() -> MailRule:
    return MailRule(
        name="Shop news",
        match=MailRuleMatch(from_value="shop.com"),
        destination="Newsletters",
    )


class TestEnsureFolders:
    def test_creates_missing_and_skips_existing(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_1", "name": "Newsletters"}],
        }
        mock_svc.users().labels().create().execute.return_value = {
            "id": "Label_2",
            "name": "Junk",
        }
        client = _make_client(mock_svc)
        result = client.ensure_folders(["Newsletters", "Junk"])
        assert result == [
            {"id": "Label_1", "name": "Newsletters"},
            {"id": "Label_2", "name": "Junk"},
        ]
        mock_svc.users().labels().create().execute.assert_called_once()


class TestListSortRules:
    def test_returns_skip_inbox_filters_only(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().settings().filters().list().execute.return_value = {
            "filter": [
                {
                    "id": "f1",
                    "criteria": {"from": "shop.com"},
                    "action": {
                        "addLabelIds": ["Label_news"],
                        "removeLabelIds": ["INBOX"],
                    },
                },
                {
                    "id": "f2",
                    "criteria": {"from": "other.com"},
                    "action": {"addLabelIds": ["STARRED"]},
                },
            ]
        }
        mock_svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_news", "name": "Newsletters"}],
        }
        client = _make_client(mock_svc)
        rules = client.list_sort_rules()
        assert len(rules) == 1
        assert rules[0].id == "f1"
        assert rules[0].destination == "Newsletters"


class TestCreateSortRule:
    def test_creates_filter_and_moves_existing(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_news", "name": "Newsletters"}],
        }
        mock_svc.users().settings().filters().create().execute.return_value = {"id": "f9"}
        mock_svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "m1"}, {"id": "m2"}],
        }
        client = _make_client(mock_svc)
        result = client.create_sort_rule(_rule(), apply_existing=True, max_existing=200)
        assert result.id == "f9"
        assert result.existing_moved == 2
        mock_svc.users().messages().batchModify.assert_called()

    def test_apply_existing_false_does_not_search(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_news", "name": "Newsletters"}],
        }
        mock_svc.users().settings().filters().create().execute.return_value = {"id": "f9"}
        client = _make_client(mock_svc)
        result = client.create_sort_rule(_rule(), apply_existing=False)
        assert result.existing_moved == 0
        mock_svc.users().messages().list().execute.assert_not_called()

    def test_403_names_settings_basic_scope(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_news", "name": "Newsletters"}],
        }
        resp = MagicMock()
        resp.status = 403
        mock_svc.users().settings().filters().create().execute.side_effect = HttpError(
            resp=resp, content=b"Forbidden"
        )
        client = _make_client(mock_svc)
        with pytest.raises(RuntimeError, match="gmail.settings.basic"):
            client.create_sort_rule(_rule(), apply_existing=False)


class TestDeleteSortRule:
    def test_deletes_filter_and_does_not_move(self) -> None:
        mock_svc = MagicMock()
        client = _make_client(mock_svc)
        client.delete_sort_rule("f9")
        mock_svc.users().settings().filters().delete.assert_called()
        mock_svc.users().messages().batchModify.assert_not_called()


class TestMoveMessages:
    def test_empty_ids_is_zero(self) -> None:
        client = _make_client()
        assert client.move_messages([], "Label_news") == {"moved": 0, "failed": 0}
