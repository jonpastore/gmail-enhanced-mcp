from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock, patch

from src.email_client import EmailClient
from src.outlook_client import OutlookClient


def _make_client() -> OutlookClient:
    token_mgr = MagicMock()
    token_mgr.get_token.return_value = "fake-token"
    client = OutlookClient(token_mgr, "test@outlook.com")
    return client


def _graph_message(
    msg_id: str = "msg_001",
    subject: str = "Test Subject",
    body_content: str = "<p>Hello</p>",
    is_read: bool = True,
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "conversationId": "conv_001",
        "subject": subject,
        "from": {"emailAddress": {"name": "Sender", "address": "sender@example.com"}},
        "toRecipients": [{"emailAddress": {"name": "Recv", "address": "recv@example.com"}}],
        "ccRecipients": [],
        "bccRecipients": [],
        "receivedDateTime": "2026-03-30T10:00:00Z",
        "body": {"contentType": "html", "content": body_content},
        "isRead": is_read,
        "flag": {"flagStatus": "notFlagged"},
        "hasAttachments": False,
        "parentFolderId": "inbox-id",
        "size": 1234,
    }


class TestImplementsInterface:
    def test_implements_email_client_interface(self) -> None:
        assert issubclass(OutlookClient, EmailClient)

    def test_provider_returns_outlook(self) -> None:
        client = _make_client()
        assert client.provider == "outlook"

    def test_email_address(self) -> None:
        client = _make_client()
        assert client.email_address == "test@outlook.com"


class TestGetProfile:
    @patch("src.outlook_client.requests")
    def test_returns_normalized(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "mail": "test@outlook.com",
            "displayName": "Test User",
        }
        mock_requests.get.return_value = mock_resp
        client = _make_client()
        result = client.get_profile()
        assert result["emailAddress"] == "test@outlook.com"
        assert "messagesTotal" in result
        assert "historyId" in result


class TestSearchMessages:
    @patch("src.outlook_client.requests")
    def test_returns_normalized(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": [_graph_message()],
            "@odata.nextLink": None,
            "@odata.count": 1,
        }
        mock_requests.get.return_value = mock_resp
        client = _make_client()
        result = client.search_messages(q="from:sender@example.com", max_results=10)
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0]["id"] == "msg_001"
        assert result["messages"][0]["threadId"] == "conv_001"
        assert "resultSizeEstimate" in result

    @patch("src.outlook_client.requests")
    def test_empty_results(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"value": []}
        mock_requests.get.return_value = mock_resp
        client = _make_client()
        result = client.search_messages(q="nonexistent")
        assert result["messages"] == []


class TestReadMessage:
    @patch("src.outlook_client.requests")
    def test_returns_gmail_format(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = _graph_message()
        mock_requests.get.return_value = mock_resp
        client = _make_client()
        result = client.read_message("msg_001")
        assert result["id"] == "msg_001"
        assert result["threadId"] == "conv_001"
        assert "payload" in result
        headers = {h["name"]: h["value"] for h in result["payload"]["headers"]}
        assert "From" in headers
        assert "Subject" in headers
        assert headers["Subject"] == "Test Subject"
        body_data = result["payload"]["body"]["data"]
        decoded = base64.urlsafe_b64decode(body_data).decode()
        assert "<p>Hello</p>" in decoded

    @patch("src.outlook_client.requests")
    def test_unread_label(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = _graph_message(is_read=False)
        mock_requests.get.return_value = mock_resp
        client = _make_client()
        result = client.read_message("msg_001")
        assert "UNREAD" in result["labelIds"]


class TestCreateDraft:
    @patch("src.outlook_client.requests")
    def test_returns_id(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "draft_001"}
        mock_resp.status_code = 201
        mock_requests.post.return_value = mock_resp
        client = _make_client()
        result = client.create_draft(to="recv@example.com", subject="Hi", body="Hello")
        assert result["id"] == "draft_001"
        assert result["message"]["id"] == "draft_001"


class TestSendEmail:
    @patch("src.outlook_client.requests")
    def test_succeeds(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_requests.post.return_value = mock_resp
        client = _make_client()
        result = client.send_email(to="recv@example.com", subject="Hi", body="Hello")
        assert result["status"] == "sent"


class TestReadThread:
    @patch("src.outlook_client.requests")
    def test_returns_thread_messages(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": [_graph_message("msg_001"), _graph_message("msg_002")],
        }
        mock_requests.get.return_value = mock_resp
        client = _make_client()
        result = client.read_thread("conv_001")
        assert result["id"] == "conv_001"
        assert len(result["messages"]) == 2


class TestListLabels:
    @patch("src.outlook_client.requests")
    def test_returns_combined(self, mock_requests: MagicMock) -> None:
        resp1 = MagicMock()
        resp1.json.return_value = {
            "value": [{"id": "inbox-id", "displayName": "Inbox"}],
        }
        resp2 = MagicMock()
        resp2.json.return_value = {
            "value": [{"id": "cat-1", "displayName": "Work", "color": "preset0"}],
        }
        mock_requests.get.side_effect = [resp1, resp2]
        client = _make_client()
        result = client.list_labels()
        assert len(result) == 2
        types = {label["type"] for label in result}
        assert types == {"system", "user"}
