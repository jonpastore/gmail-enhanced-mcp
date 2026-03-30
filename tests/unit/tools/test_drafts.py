from __future__ import annotations
from typing import Any
from unittest.mock import MagicMock
import pytest
from src.tools.drafts import (
    handle_create_draft, handle_list_drafts, handle_send_draft, handle_update_draft,
)


class TestCreateDraft:
    def test_creates_draft_returns_id(self) -> None:
        mock_client = MagicMock()
        mock_client.create_draft.return_value = {"id": "draft_001", "message": {"id": "msg_001"}}
        result = handle_create_draft({"to": "test@example.com", "subject": "Test", "body": "Hello"}, mock_client)
        assert "draft_001" in result["content"][0]["text"]
        mock_client.create_draft.assert_called_once()

    def test_with_attachments(self, tmp_path: Any) -> None:
        pdf = tmp_path / "file.pdf"
        pdf.write_bytes(b"pdf content")
        mock_client = MagicMock()
        mock_client.create_draft.return_value = {"id": "draft_002", "message": {"id": "msg_002"}}
        handle_create_draft({"to": "test@example.com", "subject": "With Attachment", "body": "See attached", "attachments": [{"type": "file", "path": str(pdf)}]}, mock_client)
        call_kwargs = mock_client.create_draft.call_args
        assert call_kwargs.kwargs.get("attachments") or call_kwargs[1].get("attachments")

    def test_body_required(self) -> None:
        with pytest.raises(ValueError, match="body is required"):
            handle_create_draft({"to": "test@example.com"}, MagicMock())


class TestUpdateDraft:
    def test_updates_existing_draft(self) -> None:
        mock_client = MagicMock()
        mock_client.update_draft.return_value = {"id": "draft_001", "message": {"id": "msg_001"}}
        result = handle_update_draft({"draftId": "draft_001", "body": "Updated body"}, mock_client)
        assert "draft_001" in result["content"][0]["text"]

    def test_draft_id_required(self) -> None:
        with pytest.raises(ValueError, match="draftId is required"):
            handle_update_draft({"body": "test"}, MagicMock())


class TestListDrafts:
    def test_returns_draft_list(self) -> None:
        mock_client = MagicMock()
        mock_client.list_drafts.return_value = {"drafts": [{"id": "d1"}, {"id": "d2"}], "nextPageToken": None}
        result = handle_list_drafts({}, mock_client)
        text = result["content"][0]["text"]
        assert "d1" in text and "d2" in text


class TestSendDraft:
    def test_sends_draft_returns_confirmation(self) -> None:
        mock_client = MagicMock()
        mock_client.send_draft.return_value = {"id": "msg_sent", "labelIds": ["SENT"]}
        result = handle_send_draft({"draftId": "draft_001"}, mock_client)
        assert "msg_sent" in result["content"][0]["text"]

    def test_draft_id_required(self) -> None:
        with pytest.raises(ValueError, match="draftId is required"):
            handle_send_draft({}, MagicMock())
