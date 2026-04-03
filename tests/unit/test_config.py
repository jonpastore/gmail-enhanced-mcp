from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from src.config import Config


class TestConfig:
    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            assert cfg.log_level == "INFO"
            assert cfg.log_file.endswith("gmail-enhanced-mcp/mcp_server.log")
            assert cfg.client_secret_path == "credentials/client_secret.json"
            assert cfg.token_path == "credentials/token.json"
            assert cfg.accounts_path == "accounts.json"
            assert cfg.mcp_auth_token is None
            assert cfg.http_port == 8420

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG", "LOG_FILE": "/tmp/test.log"}):
            cfg = Config()
            assert cfg.log_level == "DEBUG"
            assert cfg.log_file == "/tmp/test.log"

    def test_new_env_overrides(self) -> None:
        env = {
            "ACCOUNTS_PATH": "/tmp/accts.json",
            "MCP_AUTH_TOKEN": "secret123",
            "HTTP_PORT": "9000",
        }
        with patch.dict(os.environ, env):
            cfg = Config()
            assert cfg.accounts_path == "/tmp/accts.json"
            assert cfg.mcp_auth_token == "secret123"
            assert cfg.http_port == 9000

    def test_load_accounts_missing_file(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            cfg.accounts_path = str(tmp_path / "nonexistent.json")
            assert cfg.load_accounts() == []

    def test_load_accounts_from_file(self, tmp_path: Path) -> None:
        accts_file = tmp_path / "accounts.json"
        accts_file.write_text(
            json.dumps(
                {
                    "default": "a@test.com",
                    "accounts": [{"email": "a@test.com", "provider": "gmail"}],
                }
            )
        )
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            cfg.accounts_path = str(accts_file)
            accounts = cfg.load_accounts()
            assert len(accounts) == 1
            assert accounts[0]["email"] == "a@test.com"

    def test_get_default_account(self, tmp_path: Path) -> None:
        accts_file = tmp_path / "accounts.json"
        accts_file.write_text(
            json.dumps(
                {
                    "default": "a@test.com",
                    "accounts": [{"email": "a@test.com", "provider": "gmail"}],
                }
            )
        )
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            cfg.accounts_path = str(accts_file)
            assert cfg.get_default_account() == "a@test.com"

    def test_get_default_account_missing_file(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            cfg.accounts_path = str(tmp_path / "nonexistent.json")
            assert cfg.get_default_account() is None
