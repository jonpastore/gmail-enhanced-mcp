from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import ValidationError

from .models import (
    ERROR_CODES,
    InitializeParams,
    JsonRpcRequest,
    ToolCallParams,
)
from .tools import ToolRegistry

if TYPE_CHECKING:
    from .account_registry import AccountRegistry
    from .config import Config


class ProtocolHandler:
    def __init__(self) -> None:
        from .account_registry import AccountRegistry
        from .config import Config

        cfg = Config()
        registry = AccountRegistry()
        registry.load_from_config(cfg)
        calendar_ctx = self._build_calendar_ctx(cfg, registry)
        self.tool_registry = ToolRegistry(account_registry=registry, calendar_ctx=calendar_ctx)
        self.initialized = False

    @staticmethod
    def _build_calendar_ctx(cfg: Config, registry: AccountRegistry) -> Any:
        """Build CalendarContext if calendar is enabled."""
        if not cfg.calendar_enabled:
            return None
        try:
            from .auth import TokenManager
            from .calendar import GoogleCalendarClient, GoogleCalendarContext

            default_email = cfg.get_default_account()
            if not default_email:
                accounts = cfg.load_accounts()
                gmail_accounts = [a for a in accounts if a.get("provider") == "gmail"]
                if gmail_accounts:
                    default_email = gmail_accounts[0]["email"]
            if not default_email:
                return None
            token_path = f"credentials/{default_email}/token.json"
            tmgr = TokenManager(cfg.client_secret_path, token_path)
            client = GoogleCalendarClient(tmgr, user_timezone=cfg.user_timezone)
            return GoogleCalendarContext(client)
        except Exception:
            return None

    def handle_request(self, raw_request: dict[str, Any]) -> dict[str, Any] | None:
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

    def _get_method_handler(self, method: str) -> Any | None:
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

    def _success_response(self, result: Any, request_id: int | str | None) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "result": result, "id": request_id}

    def _error_response(
        self, code: int, message: str, request_id: int | str | None
    ) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": request_id,
        }
