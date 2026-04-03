from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

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
        self.log_file: str = os.getenv(
            "LOG_FILE",
            str(self._default_log_path()),
        )
        self.ssl_cert_path: str | None = os.getenv("SSL_CERT_PATH")
        self.ssl_key_path: str | None = os.getenv("SSL_KEY_PATH")
        self.cache_db_path: str = os.getenv("TRIAGE_CACHE_DB", "data/triage_cache.db")
        self.triage_config_path: str = os.getenv("TRIAGE_CONFIG", "data/triage_config.json")
        self.calendar_enabled: bool = os.getenv("CALENDAR_ENABLED", "false").lower() == "true"
        self.user_timezone: str = os.getenv("USER_TIMEZONE", "America/New_York")
        self.digest_frequency: str = os.getenv("DIGEST_FREQUENCY", "daily")
        self.digest_time: str = os.getenv("DIGEST_TIME", "08:00")
        self.digest_day: str = os.getenv("DIGEST_DAY", "monday")
        self.digest_timezone: str = os.getenv("DIGEST_TIMEZONE", self.user_timezone)
        self.accounts_path: str = os.getenv("ACCOUNTS_PATH", "accounts.json")
        self.mcp_auth_token: str | None = os.getenv("MCP_AUTH_TOKEN")
        self.http_port: int = int(os.getenv("HTTP_PORT", "8420"))
        self.ssl_cert_path: str | None = os.getenv("SSL_CERT_PATH")
        self.ssl_key_path: str | None = os.getenv("SSL_KEY_PATH")
        self.cache_db_path: str = os.getenv("TRIAGE_CACHE_DB", "data/triage_cache.db")
        self.triage_config_path: str = os.getenv("TRIAGE_CONFIG", "data/triage_config.json")
        self.calendar_enabled: bool = os.getenv("CALENDAR_ENABLED", "false").lower() == "true"
        self.user_timezone: str = os.getenv("USER_TIMEZONE", "America/New_York")
        self.digest_frequency: str = os.getenv("DIGEST_FREQUENCY", "daily")
        self.digest_time: str = os.getenv("DIGEST_TIME", "08:00")
        self.digest_day: str = os.getenv("DIGEST_DAY", "monday")
        self.digest_timezone: str = os.getenv("DIGEST_TIMEZONE", self.user_timezone)

    @staticmethod
    def _default_log_path() -> Path:
        """Return a platform-appropriate writable log path."""
        if platform.system() == "Darwin":
            return Path.home() / "Library" / "Logs" / "gmail-enhanced-mcp" / "mcp_server.log"
        # Linux: use XDG_STATE_HOME or ~/.local/state
        state_dir = os.getenv("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
        return Path(state_dir) / "gmail-enhanced-mcp" / "mcp_server.log"

    def load_accounts(self) -> list[dict[str, Any]]:
        path = Path(self.accounts_path)
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        return data.get("accounts", [])

    def get_default_account(self) -> str | None:
        path = Path(self.accounts_path)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return data.get("default")


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
        Path(cfg.log_file).parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            cfg.log_file,
            rotation="10 MB",
            retention=3,
            level=cfg.log_level,
        )
