from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.auth import TokenManager


class TestTokenManager:
    def test_load_token_from_file(self, tmp_path: Path) -> None:
        token_data = {
            "token": "access_123",
            "refresh_token": "refresh_456",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        }
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps(token_data))

        mgr = TokenManager(
            client_secret_path=str(tmp_path / "client_secret.json"),
            token_path=str(token_file),
        )
        creds = mgr.load_token()
        assert creds is not None

    def test_load_token_returns_none_when_missing(self, tmp_path: Path) -> None:
        mgr = TokenManager(
            client_secret_path=str(tmp_path / "client_secret.json"),
            token_path=str(tmp_path / "nonexistent.json"),
        )
        creds = mgr.load_token()
        assert creds is None

    def test_save_token_writes_file(self, tmp_path: Path) -> None:
        token_file = tmp_path / "token.json"
        mgr = TokenManager(
            client_secret_path=str(tmp_path / "client_secret.json"),
            token_path=str(token_file),
        )
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "saved"}'
        mgr.save_token(mock_creds)
        assert token_file.exists()
        assert json.loads(token_file.read_text()) == {"token": "saved"}

    def test_get_credentials_refreshes_expired_token(self, tmp_path: Path) -> None:
        token_data = {
            "token": "expired",
            "refresh_token": "refresh_456",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "cid",
            "client_secret": "csec",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        }
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps(token_data))

        mgr = TokenManager(
            client_secret_path=str(tmp_path / "cs.json"),
            token_path=str(token_file),
        )

        with patch("src.auth.Credentials") as mock_creds_cls:
            mock_creds = MagicMock()
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = "refresh_456"
            mock_creds.to_json.return_value = '{"token": "refreshed"}'
            mock_creds_cls.from_authorized_user_info.return_value = mock_creds

            mgr.get_credentials()
            mock_creds.refresh.assert_called_once()

    def test_get_credentials_raises_when_no_token(self, tmp_path: Path) -> None:
        mgr = TokenManager(
            client_secret_path=str(tmp_path / "cs.json"),
            token_path=str(tmp_path / "missing.json"),
        )
        with pytest.raises(RuntimeError, match="Not authenticated"):
            mgr.get_credentials()
