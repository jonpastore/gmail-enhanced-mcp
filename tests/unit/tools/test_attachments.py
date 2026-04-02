from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.handler_context import HandlerContext
from src.tools.attachments import handle_download_attachment


def _ctx(client=None) -> HandlerContext:
    return HandlerContext(client=client or MagicMock())


class TestDownloadAttachment:
    def test_downloads_and_saves(self, tmp_path) -> None:
        mock_client = MagicMock()
        save = f"{tmp_path}/out.pdf"
        mock_client.download_attachment.return_value = save
        result = handle_download_attachment(
            {"messageId": "msg_001", "attachmentId": "att_001", "savePath": save}, _ctx(mock_client)
        )
        assert save in result["content"][0]["text"]

    def test_message_id_required(self) -> None:
        with pytest.raises(ValueError, match="messageId is required"):
            handle_download_attachment({"attachmentId": "a", "savePath": "/tmp/x"}, _ctx())

    def test_attachment_id_required(self) -> None:
        with pytest.raises(ValueError, match="attachmentId is required"):
            handle_download_attachment({"messageId": "m", "savePath": "/tmp/x"}, _ctx())

    def test_save_path_required(self) -> None:
        with pytest.raises(ValueError, match="savePath is required"):
            handle_download_attachment({"messageId": "m", "attachmentId": "a"}, _ctx())
