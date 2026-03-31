from __future__ import annotations

import sys

from loguru import logger

from .config import Config, setup_logging


def main() -> None:
    cfg = Config()
    setup_logging(cfg)

    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        provider = "gmail"
        for i, arg in enumerate(sys.argv):
            if arg == "--provider" and i + 1 < len(sys.argv):
                provider = sys.argv[i + 1]
        from .auth import run_auth_flow

        run_auth_flow(cfg, provider=provider)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        port = cfg.http_port
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        from .http_server import run_http_server

        run_http_server(cfg, port=port)
        return

    try:
        logger.info("Starting Gmail Enhanced MCP Server v2.0.0 (stdio)")
        from .protocol import ProtocolHandler
        from .server import StdioServer

        server = StdioServer()
        handler = ProtocolHandler()
        server.run(handler.handle_request)
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
