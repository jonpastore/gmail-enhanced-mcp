from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from src.gmail_client import GmailClient, SyncProvider


def _make_client(mock_service: MagicMock | None = None) -> GmailClient:
    client = GmailClient.__new__(GmailClient)
    client._service = mock_service or MagicMock()
    client._account_email = "test@gmail.com"
    return client


class TestGetProfile:
    def test_returns_profile_data(self, sample_profile: dict[str, Any]) -> None:
        mock_svc = MagicMock()
        mock_svc.users().getProfile().execute.return_value = sample_profile
        client = _make_client(mock_svc)
        result = client.get_profile()
        assert result["emailAddress"] == "jpastore79@gmail.com"


class TestSearchMessages:
    def test_returns_messages_list(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_001", "threadId": "t_001"}],
            "resultSizeEstimate": 1,
        }
        client = _make_client(mock_svc)
        result = client.search_messages(q="from:test@example.com", max_results=10)
        assert len(result["messages"]) == 1

    def test_empty_results(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        client = _make_client(mock_svc)
        result = client.search_messages(q="nonexistent")
        assert result["messages"] == []


class TestReadMessage:
    def test_returns_full_message(self, sample_message: dict[str, Any]) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = sample_message
        client = _make_client(mock_svc)
        result = client.read_message("msg_001")
        assert result["id"] == "msg_001"


class TestReadThread:
    def test_returns_thread_with_messages(self, sample_thread: dict[str, Any]) -> None:
        mock_svc = MagicMock()
        mock_svc.users().threads().get().execute.return_value = sample_thread
        client = _make_client(mock_svc)
        result = client.read_thread("thread_001")
        assert result["id"] == "thread_001"
        assert len(result["messages"]) == 1


class TestBuildMimeMessage:
    def test_plain_text_no_attachments(self) -> None:
        client = _make_client()
        mime_msg = client.build_mime_message(
            to="test@example.com",
            subject="Test",
            body="Hello",
            content_type="text/plain",
        )
        assert mime_msg["To"] == "test@example.com"
        assert mime_msg["Subject"] == "Test"

    def test_with_file_attachment(self, tmp_path: Any) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test content")
        client = _make_client()
        mime_msg = client.build_mime_message(
            to="test@example.com",
            subject="Test",
            body="See attached",
            content_type="text/plain",
            attachments=[{"type": "file", "path": str(pdf)}],
        )
        assert mime_msg.get_content_type() == "multipart/mixed"

    def test_missing_file_raises(self) -> None:
        client = _make_client()
        with pytest.raises(FileNotFoundError, match="does not exist"):
            client.build_mime_message(
                to="test@example.com",
                subject="Test",
                body="Hello",
                content_type="text/plain",
                attachments=[{"type": "file", "path": "/nonexistent/file.pdf"}],
            )


class TestCreateDraft:
    def test_creates_draft_and_returns_id(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().drafts().create().execute.return_value = {
            "id": "draft_001",
            "message": {"id": "msg_draft_001"},
        }
        client = _make_client(mock_svc)
        result = client.create_draft(
            to="test@example.com",
            subject="Draft Test",
            body="Body",
            content_type="text/plain",
        )
        assert result["id"] == "draft_001"


class TestSendDraft:
    def test_sends_draft_by_id(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().drafts().send().execute.return_value = {
            "id": "msg_sent_001",
            "labelIds": ["SENT"],
        }
        client = _make_client(mock_svc)
        result = client.send_draft("draft_001")
        assert result["id"] == "msg_sent_001"


class TestSendEmail:
    def test_sends_email_directly(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().send().execute.return_value = {
            "id": "msg_sent_002",
            "labelIds": ["SENT"],
        }
        client = _make_client(mock_svc)
        result = client.send_email(
            to="test@example.com",
            subject="Direct Send",
            body="Body",
            content_type="text/plain",
        )
        assert result["id"] == "msg_sent_002"


class TestHistorySync:
    def test_returns_added_deleted_label_changes(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().history().list().execute.return_value = {
            "history": [
                {
                    "id": "100",
                    "messagesAdded": [{"message": {"id": "msg1", "threadId": "t1"}}],
                    "messagesDeleted": [{"message": {"id": "msg2"}}],
                    "labelsAdded": [{"message": {"id": "msg3"}, "labelIds": ["IMPORTANT"]}],
                    "labelsRemoved": [{"message": {"id": "msg4"}, "labelIds": ["UNREAD"]}],
                }
            ],
            "historyId": "200",
        }
        client = _make_client(mock_svc)
        result = client.history_sync(start_history_id="50")
        assert result["history_id"] == "200"
        assert result["added"] == ["msg1"]
        assert result["deleted"] == ["msg2"]
        assert len(result["label_changes"]) == 2

    def test_empty_history_no_changes(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().history().list().execute.return_value = {
            "historyId": "200",
        }
        client = _make_client(mock_svc)
        result = client.history_sync(start_history_id="200")
        assert result["history_id"] == "200"
        assert result["added"] == []
        assert result["deleted"] == []
        assert result["label_changes"] == []
        assert "full_sync_required" not in result

    def test_expired_history_id_returns_full_sync_required(self) -> None:
        mock_svc = MagicMock()
        resp = MagicMock()
        resp.status = 404
        mock_svc.users().history().list().execute.side_effect = HttpError(
            resp=resp, content=b"Not Found"
        )
        client = _make_client(mock_svc)
        result = client.history_sync(start_history_id="1")
        assert result["full_sync_required"] is True
        assert result["added"] == []
        assert result["deleted"] == []
        assert result["label_changes"] == []

    def test_non_404_http_error_is_raised(self) -> None:
        mock_svc = MagicMock()
        resp = MagicMock()
        resp.status = 500
        mock_svc.users().history().list().execute.side_effect = HttpError(
            resp=resp, content=b"Internal Server Error"
        )
        client = _make_client(mock_svc)
        with pytest.raises(HttpError):
            client.history_sync(start_history_id="50")

    def test_handles_pagination(self) -> None:
        mock_svc = MagicMock()
        page1 = {
            "history": [
                {"id": "100", "messagesAdded": [{"message": {"id": "msg1"}}]},
            ],
            "historyId": "150",
            "nextPageToken": "token_abc",
        }
        page2 = {
            "history": [
                {"id": "150", "messagesAdded": [{"message": {"id": "msg2"}}]},
            ],
            "historyId": "200",
        }
        mock_svc.users().history().list().execute.side_effect = [page1, page2]
        client = _make_client(mock_svc)
        result = client.history_sync(start_history_id="50")
        assert result["history_id"] == "200"
        assert set(result["added"]) == {"msg1", "msg2"}

    def test_extracts_new_history_id_watermark(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().history().list().execute.return_value = {
            "history": [],
            "historyId": "99999",
        }
        client = _make_client(mock_svc)
        result = client.history_sync(start_history_id="50")
        assert result["history_id"] == "99999"

    def test_multiple_history_entries_aggregated(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().history().list().execute.return_value = {
            "history": [
                {"id": "100", "messagesAdded": [{"message": {"id": "msg1"}}]},
                {
                    "id": "110",
                    "messagesAdded": [{"message": {"id": "msg2"}}],
                    "messagesDeleted": [{"message": {"id": "msg3"}}],
                },
            ],
            "historyId": "200",
        }
        client = _make_client(mock_svc)
        result = client.history_sync(start_history_id="50")
        assert result["added"] == ["msg1", "msg2"]
        assert result["deleted"] == ["msg3"]

    def test_gmail_client_matches_sync_provider_protocol(self) -> None:
        client = _make_client()
        assert isinstance(client, SyncProvider)
        import inspect

        sig = inspect.signature(GmailClient.history_sync)
        params = list(sig.parameters.keys())
        assert "start_history_id" in params
        assert "max_results" in params


class TestTrashMessages:
    def test_trashes_single_message(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.trash_messages(["msg_001"])
        assert result["trashed_count"] == 1
        assert result["message_ids"] == ["msg_001"]

    def test_trashes_multiple_messages(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.trash_messages(["msg_001", "msg_002", "msg_003"])
        assert result["trashed_count"] == 3

    def test_empty_list_returns_zero(self) -> None:
        client = _make_client()
        result = client.trash_messages([])
        assert result["trashed_count"] == 0
        assert result["message_ids"] == []


class TestTrashByQuery:
    def test_searches_and_trashes(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "messages": [
                {"id": "msg_001", "threadId": "t_001"},
                {"id": "msg_002", "threadId": "t_002"},
            ],
            "resultSizeEstimate": 2,
        }
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.trash_by_query("from:spam@example.com")
        assert result["trashed_count"] == 2

    def test_no_results_returns_zero(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        client = _make_client(mock_svc)
        result = client.trash_by_query("from:nobody@example.com")
        assert result["trashed_count"] == 0
        assert result["message_ids"] == []


class TestCreateBlockFilter:
    def test_creates_filter_and_trashes_existing(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().settings().filters().create().execute.return_value = {
            "id": "filter_001",
        }
        mock_svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_001", "threadId": "t_001"}],
            "resultSizeEstimate": 1,
        }
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.create_block_filter("spam@example.com")
        assert result["filter_id"] == "filter_001"
        assert result["existing_trashed"] == 1

    def test_creates_filter_no_existing_messages(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().settings().filters().create().execute.return_value = {
            "id": "filter_002",
        }
        mock_svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        client = _make_client(mock_svc)
        result = client.create_block_filter("nobody@example.com")
        assert result["filter_id"] == "filter_002"
        assert result["existing_trashed"] == 0


class TestReportSpam:
    def test_reports_messages_as_spam(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().batchModify().execute.return_value = {}
        client = _make_client(mock_svc)
        result = client.report_spam(["msg_001", "msg_002"])
        assert result["reported_count"] == 2

    def test_empty_list_returns_zero(self) -> None:
        client = _make_client()
        result = client.report_spam([])
        assert result["reported_count"] == 0


class TestGetContacts:
    def test_returns_contacts_with_emails(self) -> None:
        mock_svc = MagicMock()
        client = _make_client(mock_svc)
        client._token_mgr = MagicMock()
        mock_people = MagicMock()
        mock_people.people().connections().list().execute.return_value = {
            "connections": [
                {
                    "names": [{"displayName": "Alice Smith"}],
                    "emailAddresses": [{"value": "alice@example.com"}],
                },
                {
                    "names": [{"displayName": "Bob Jones"}],
                    "emailAddresses": [
                        {"value": "bob@example.com"},
                        {"value": "bob@work.com"},
                    ],
                },
                {
                    "names": [{"displayName": "No Email"}],
                },
            ],
        }
        with patch("src.gmail_client.build", return_value=mock_people):
            result = client.get_contacts(max_results=100)
        assert len(result) == 2
        assert result[0]["name"] == "Alice Smith"
        assert result[0]["emails"] == ["alice@example.com"]
        assert result[1]["emails"] == ["bob@example.com", "bob@work.com"]

    def test_paginates_through_all_contacts(self) -> None:
        mock_svc = MagicMock()
        client = _make_client(mock_svc)
        client._token_mgr = MagicMock()
        mock_people = MagicMock()
        page1 = {
            "connections": [
                {
                    "names": [{"displayName": "Alice"}],
                    "emailAddresses": [{"value": "alice@test.com"}],
                },
            ],
            "nextPageToken": "page2",
        }
        page2 = {
            "connections": [
                {
                    "names": [{"displayName": "Bob"}],
                    "emailAddresses": [{"value": "bob@test.com"}],
                },
            ],
        }
        mock_people.people().connections().list().execute.side_effect = [page1, page2]
        with patch("src.gmail_client.build", return_value=mock_people):
            result = client.get_contacts(max_results=2000)
        assert len(result) == 2


class TestExtractUnsubscribeLink:
    def test_extracts_https_link(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {
                "headers": [
                    {
                        "name": "List-Unsubscribe",
                        "value": "<https://example.com/unsub?id=123>",
                    },
                ],
            },
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is True
        assert result["unsubscribe_url"] == "https://example.com/unsub?id=123"
        assert result["unsubscribe_mailto"] is None

    def test_extracts_mailto_link(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {
                "headers": [
                    {
                        "name": "List-Unsubscribe",
                        "value": "<mailto:unsub@example.com?subject=unsub>",
                    },
                ],
            },
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is True
        assert result["unsubscribe_mailto"] == "mailto:unsub@example.com?subject=unsub"
        assert result["unsubscribe_url"] is None

    def test_extracts_both(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {
                "headers": [
                    {
                        "name": "List-Unsubscribe",
                        "value": "<mailto:unsub@example.com>, <https://example.com/unsub>",
                    },
                ],
            },
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is True
        assert result["unsubscribe_url"] == "https://example.com/unsub"
        assert result["unsubscribe_mailto"] == "mailto:unsub@example.com"

    def test_no_header_returns_not_found(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {"headers": [{"name": "Subject", "value": "Hello"}]},
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is False
