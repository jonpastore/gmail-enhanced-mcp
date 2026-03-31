from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from loguru import logger

load_dotenv()


class Config:
    def __init__(self) -> None:
        self.client_secret_path: str = os.getenv(
            "GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json"
        )
        self.token_path: str = os.getenv("GOOGLE_TOKEN_PATH", "credentials/token.json")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_file: str = os.getenv("LOG_FILE", "mcp_server.log")


def setup_logging(cfg: Config) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=cfg.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    if cfg.log_file:
        logger.add(
            cfg.log_file,
            rotation="10 MB",
            retention=3,
            level=cfg.log_level,
        )
