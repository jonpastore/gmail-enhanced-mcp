from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from loguru import logger
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .account_registry import AccountRegistry
from .config import Config
from .models import ToolCallParams
from .tools import ToolRegistry


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, token: str, exempt_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self._token = token
        self._exempt = exempt_paths or {"/health"}

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path in self._exempt:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self._token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_mcp_server(tool_registry: ToolRegistry) -> Server:
    server = Server("gmail-enhanced-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = tool_registry.list_tools()
        return [
            Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t["inputSchema"],
            )
            for t in tools
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        params = ToolCallParams(name=name, arguments=arguments)
        result = tool_registry.execute_tool(params)
        content = result.get("content", [])
        return [TextContent(type="text", text=c.get("text", "")) for c in content]

    return server


def create_app(cfg: Config) -> Starlette:
    registry = AccountRegistry()
    registry.load_from_config(cfg)
    tool_registry = ToolRegistry(account_registry=registry)
    mcp_server = create_mcp_server(tool_registry)
    session_manager = StreamableHTTPSessionManager(app=mcp_server)

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "version": "2.0.0"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("HTTP server started")
            yield
            logger.info("HTTP server stopped")

    middleware: list[Middleware] = []
    if cfg.mcp_auth_token:
        middleware.append(
            Middleware(BearerAuthMiddleware, token=cfg.mcp_auth_token, exempt_paths={"/health"})
        )

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=session_manager.handle_request),
        ],
        lifespan=lifespan,
        middleware=middleware,
    )


def run_http_server(cfg: Config, port: int = 8420) -> None:
    if not cfg.mcp_auth_token:
        logger.warning("MCP_AUTH_TOKEN not set - HTTP server running without auth!")
    logger.info(f"Starting HTTP server on port {port}")
    app = create_app(cfg)
    uvicorn.run(app, host="0.0.0.0", port=port)
