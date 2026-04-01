from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
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
from starlette.staticfiles import StaticFiles

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
        path = request.url.path
        logger.info(
            f"REQ {request.method} {path} | "
            f"Accept: {request.headers.get('accept', 'MISSING')} | "
            f"Content-Type: {request.headers.get('content-type', 'MISSING')} | "
            f"Auth: {'Bearer ...' if request.headers.get('authorization', '').startswith('Bearer ') else request.headers.get('authorization', 'MISSING')[:20]} | "
            f"Origin: {request.headers.get('origin', 'NONE')}"
        )
        if path in self._exempt or any(path.startswith(p) for p in self._exempt if p.endswith("/")):
            return await call_next(request)
        if request.method == "OPTIONS":
            return self._cors_response()
        auth = request.headers.get("authorization", "")
        query_token = request.query_params.get("token", "")
        if auth.startswith("Bearer ") and auth[7:] == self._token:
            resp = await call_next(request)
            self._add_cors_headers(resp)
            return resp
        if query_token == self._token:
            resp = await call_next(request)
            self._add_cors_headers(resp)
            return resp
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    def _cors_response(self) -> JSONResponse:
        return JSONResponse(
            {},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Mcp-Session-Id",
                "Access-Control-Expose-Headers": "Mcp-Session-Id",
            },
        )

    @staticmethod
    def _add_cors_headers(resp: Any) -> None:
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id"


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

    async def restart(request: Request) -> JSONResponse:
        import os
        import subprocess
        import sys
        import threading

        logger.info("Restart requested — spawning new process and exiting")

        def _restart() -> None:
            import time
            time.sleep(1)
            env = os.environ.copy()
            subprocess.Popen(
                [sys.executable] + sys.argv,
                env=env,
                start_new_session=True,
            )
            time.sleep(1)
            os._exit(0)

        threading.Thread(target=_restart, daemon=False).start()
        return JSONResponse({"status": "restarting"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("HTTP server started")
            yield
            logger.info("HTTP server stopped")

    middleware: list[Middleware] = []
    if cfg.mcp_auth_token:
        middleware.append(
            Middleware(BearerAuthMiddleware, token=cfg.mcp_auth_token, exempt_paths={"/health", "/ui/"})
        )

    ui_dir = Path(__file__).parent / "ui"

    return Starlette(
        routes=[
            Route("/health", health),
            Route("/restart", restart, methods=["POST"]),
            Mount("/mcp", app=session_manager.handle_request),
            Mount("/ui", app=StaticFiles(directory=str(ui_dir), html=True), name="ui"),
        ],
        lifespan=lifespan,
        middleware=middleware,
    )


def run_http_server(cfg: Config, port: int = 8420) -> None:
    if not cfg.mcp_auth_token:
        logger.warning("MCP_AUTH_TOKEN not set - HTTP server running without auth!")
    app = create_app(cfg)

    ssl_cert = cfg.ssl_cert_path
    ssl_key = cfg.ssl_key_path
    if ssl_cert and ssl_key:
        logger.info(f"Starting HTTPS server on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port, ssl_certfile=ssl_cert, ssl_keyfile=ssl_key)
    else:
        logger.info(f"Starting HTTP server on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port)
