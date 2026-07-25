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


class TestDraftRegressions:
    """Four bugs found 2026-07-25 while drafting a client email through this bridge.

    Every one of them failed SILENTLY — the calls returned success and did the wrong thing,
    which cost a real draft its body twice before the pattern was spotted.
    """

    def test_update_draft_does_not_wipe_the_body_when_only_cc_is_given(self) -> None:
        """`body` defaults to "" and _build_graph_message always emits a body block, so a
        cc-only update used to PATCH the draft's content to empty."""
        client = _make_client()
        with patch.object(client, "_graph_patch", return_value={"id": "d1"}) as patched:
            client.update_draft("d1", cc="a@b.com")
        sent = patched.call_args[0][1]
        assert "body" not in sent, "an unsupplied body must not be PATCHed"
        assert sent["ccRecipients"] == [{"emailAddress": {"address": "a@b.com"}}]

    def test_update_draft_still_sets_the_body_when_given_one(self) -> None:
        client = _make_client()
        with patch.object(client, "_graph_patch", return_value={"id": "d1"}) as patched:
            client.update_draft("d1", body="hello", content_type="text/html")
        sent = patched.call_args[0][1]
        assert sent["body"] == {"contentType": "HTML", "content": "hello"}

    def test_thread_id_creates_a_real_reply_not_a_new_conversation(self) -> None:
        """conversationId is read-only on Graph: POSTing it is accepted and ignored, so the
        'reply' landed in a brand-new thread. Only createReplyAll actually threads."""
        client = _make_client()
        posted: list[str] = []

        def fake_post(path: str, json_body: dict | None = None) -> Any:
            posted.append(path)
            resp = MagicMock()
            resp.json.return_value = {"id": "reply_draft"}
            return resp

        thread_msgs = {"value": [{"id": "m1", "receivedDateTime": "2026-01-01"}]}
        with patch.object(client, "_graph_get", return_value=thread_msgs), \
             patch.object(client, "_graph_post", side_effect=fake_post), \
             patch.object(client, "_graph_patch", return_value={"id": "reply_draft"}):
            result = client.create_draft(to="x@y.com", subject="s", body="b", thread_id="conv_9")

        assert result["id"] == "reply_draft"
        assert any("createReplyAll" in p for p in posted), posted
        assert not any(p == "/me/messages" for p in posted), "must not POST a standalone message"

    def test_read_thread_does_not_send_orderby(self) -> None:
        """Graph 400s on $filter(conversationId) + $orderby; sort client-side instead."""
        client = _make_client()
        with patch.object(client, "_graph_get", return_value={"value": []}) as got:
            client.read_thread("conv_1")
        assert "$orderby" not in got.call_args[1]["params"]

    def test_read_thread_sorts_oldest_first(self) -> None:
        client = _make_client()
        newer = _graph_message("m2")
        newer["receivedDateTime"] = "2026-05-01T10:00:00Z"
        older = _graph_message("m1")
        older["receivedDateTime"] = "2026-01-01T10:00:00Z"
        with patch.object(client, "_graph_get", return_value={"value": [newer, older]}):
            thread = client.read_thread("conv_1")
        assert [m["id"] for m in thread["messages"]] == ["m1", "m2"]

    def test_attachments_surface_as_parts_with_a_downloadable_id(self) -> None:
        """Outlook messages always reported `parts: []`, so callers could neither see an
        attachment nor obtain the id that gmail_download_attachment requires."""
        client = _make_client()
        msg = _graph_message()
        msg["hasAttachments"] = True
        att = {"value": [{"id": "att1", "name": "x.pdf",
                          "contentType": "application/pdf", "size": 99}]}
        with patch.object(client, "_graph_get", return_value=att):
            normalized = client._normalize_message(msg)
        parts = normalized["payload"]["parts"]
        assert parts[0]["filename"] == "x.pdf"
        assert parts[0]["body"]["attachmentId"] == "att1"

    def test_cc_is_emitted_as_a_header(self) -> None:
        """_format_message only prints headers that exist; without this a real Cc read back
        as if the recipients had been dropped."""
        client = _make_client()
        msg = _graph_message()
        msg["ccRecipients"] = [{"emailAddress": {"name": "C", "address": "c@d.com"}}]
        headers = client._normalize_message(msg)["payload"]["headers"]
        assert any(h["name"] == "Cc" and "c@d.com" in h["value"] for h in headers)
