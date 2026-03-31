from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.gmail_client import GmailClient


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
