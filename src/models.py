from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, field_validator


class JsonRpcRequest(BaseModel):
    jsonrpc: str
    method: str
    params: Optional[dict[str, Any]] = None
    id: Optional[Union[int, str]] = None

    @field_validator("jsonrpc")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "2.0":
            raise ValueError(f"Invalid JSON-RPC version: {v}")
        return v


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict[str, Any]] = None
    id: Optional[Union[int, str]] = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class InitializeParams(BaseModel):
    protocolVersion: str
    capabilities: dict[str, Any] = {}
    clientInfo: Optional[dict[str, str]] = None


class ToolCallParams(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class AttachmentSource(BaseModel):
    type: str
    path: Optional[str] = None
    message_id: Optional[str] = None
    attachment_id: Optional[str] = None
    url: Optional[str] = None
    filename: Optional[str] = None

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
