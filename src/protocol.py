from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from pydantic import ValidationError

from .models import (
    ERROR_CODES,
    InitializeParams,
    JsonRpcRequest,
    ToolCallParams,
)
from .tools import ToolRegistry


class ProtocolHandler:
    def __init__(self) -> None:
        from .config import Config
        from .gmail_client import GmailClient

        cfg = Config()
        client = GmailClient(cfg)
        self.tool_registry = ToolRegistry(gmail_client=client)
        self.initialized = False

    def handle_request(self, raw_request: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            request = JsonRpcRequest(**raw_request)

            if request.id is None and request.method == "initialized":
                logger.info("Received 'initialized' notification")
                self.initialized = True
                return None

            method_handler = self._get_method_handler(request.method)
            if not method_handler:
                return self._error_response(
                    ERROR_CODES["METHOD_NOT_FOUND"],
                    f"Method not found: {request.method}",
                    request.id,
                )

            result = method_handler(request.params or {})
            return self._success_response(result, request.id)

        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return self._error_response(
                ERROR_CODES["INVALID_REQUEST"],
                f"Invalid request: {e}",
                raw_request.get("id"),
            )
        except ValueError as e:
            logger.error(f"Value error: {e}")
            return self._error_response(
                ERROR_CODES["INVALID_PARAMS"],
                str(e),
                raw_request.get("id"),
            )
        except Exception as e:
            logger.error(f"Internal error: {e}")
            return self._error_response(
                ERROR_CODES["INTERNAL_ERROR"],
                f"Internal error: {e}",
                raw_request.get("id"),
            )

    def _get_method_handler(self, method: str) -> Optional[Any]:
        handlers: dict[str, Any] = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
        }
        return handlers.get(method)

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        init_params = InitializeParams(**params)
        logger.info(f"Initializing with protocol version: {init_params.protocolVersion}")
        self.initialized = True
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "gmail-enhanced-mcp", "version": "1.0.0"},
        }

    def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        tools = self.tool_registry.list_tools()
        return {"tools": tools}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.initialized:
            raise ValueError("Server not initialized")
        tool_params = ToolCallParams(**params)
        return self.tool_registry.execute_tool(tool_params)

    def _success_response(
        self, result: Any, request_id: Optional[int | str]
    ) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "result": result, "id": request_id}

    def _error_response(
        self, code: int, message: str, request_id: Optional[int | str]
    ) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": request_id,
        }
