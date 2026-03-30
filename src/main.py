from __future__ import annotations

import sys

from loguru import logger

from .config import Config, setup_logging
from .protocol import ProtocolHandler
from .server import StdioServer


def main() -> None:
    cfg = Config()
    setup_logging(cfg)

    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        from .auth import run_auth_flow

        run_auth_flow(cfg)
        return

    try:
        logger.info("Starting Gmail Enhanced MCP Server v1.0.0")
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
