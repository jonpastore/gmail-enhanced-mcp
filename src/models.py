from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


class JsonRpcRequest(BaseModel):
    jsonrpc: str
    method: str
    params: dict[str, Any] | None = None
    id: int | str | None = None

    @field_validator("jsonrpc")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "2.0":
            raise ValueError(f"Invalid JSON-RPC version: {v}")
        return v


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Any | None = None
    error: dict[str, Any] | None = None
    id: int | str | None = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class InitializeParams(BaseModel):
    protocolVersion: str
    capabilities: dict[str, Any] = {}
    clientInfo: dict[str, str] | None = None


class ToolCallParams(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class AttachmentSource(BaseModel):
    type: str
    path: str | None = None
    message_id: str | None = None
    attachment_id: str | None = None
    url: str | None = None
    filename: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("file", "gmail", "url"):
            raise ValueError(f"Invalid attachment type: {v}. Must be file, gmail, or url")
        return v


ERROR_CODES: dict[str, int] = {
    "PARSE_ERROR": -32700,
    "INVALID_REQUEST": -32600,
    "METHOD_NOT_FOUND": -32601,
    "INVALID_PARAMS": -32602,
    "INTERNAL_ERROR": -32603,
    "SERVER_ERROR": -32000,
}
