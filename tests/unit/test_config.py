from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config


class TestConfig:
    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            assert cfg.log_level == "INFO"
            assert cfg.log_file == "mcp_server.log"
            assert cfg.client_secret_path == "credentials/client_secret.json"
            assert cfg.token_path == "credentials/token.json"

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG", "LOG_FILE": "/tmp/test.log"}):
            cfg = Config()
            assert cfg.log_level == "DEBUG"
            assert cfg.log_file == "/tmp/test.log"
