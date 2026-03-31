from __future__ import annotations

import pytest

from src.models import (
    ERROR_CODES,
    AttachmentSource,
    JsonRpcRequest,
    ToolCallParams,
)


class TestJsonRpcRequest:
    def test_valid_request_parses(self) -> None:
        req = JsonRpcRequest(jsonrpc="2.0", method="tools/list", id=1)
        assert req.method == "tools/list"
        assert req.id == 1

    def test_invalid_jsonrpc_version_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON-RPC version"):
            JsonRpcRequest(jsonrpc="1.0", method="test", id=1)

    def test_params_default_to_none(self) -> None:
        req = JsonRpcRequest(jsonrpc="2.0", method="test", id=1)
        assert req.params is None


class TestToolCallParams:
    def test_valid_tool_call(self) -> None:
        params = ToolCallParams(name="gmail_search_messages", arguments={"q": "test"})
        assert params.name == "gmail_search_messages"
        assert params.arguments == {"q": "test"}

    def test_arguments_default_to_empty(self) -> None:
        params = ToolCallParams(name="gmail_get_profile")
        assert params.arguments == {}


class TestAttachmentSource:
    def test_file_attachment(self) -> None:
        att = AttachmentSource(type="file", path="/tmp/test.pdf")
        assert att.type == "file"
        assert att.path == "/tmp/test.pdf"

    def test_gmail_attachment(self) -> None:
        att = AttachmentSource(type="gmail", message_id="abc", attachment_id="def")
        assert att.type == "gmail"

    def test_url_attachment(self) -> None:
        att = AttachmentSource(type="url", url="https://example.com/doc.pdf", filename="doc.pdf")
        assert att.type == "url"

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError):
            AttachmentSource(type="ftp", path="/tmp/test.pdf")


class TestErrorCodes:
    def test_standard_codes_present(self) -> None:
        assert ERROR_CODES["PARSE_ERROR"] == -32700
        assert ERROR_CODES["METHOD_NOT_FOUND"] == -32601
        assert ERROR_CODES["INTERNAL_ERROR"] == -32603
