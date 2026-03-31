from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.auth import MicrosoftTokenManager


class TestMicrosoftTokenManager:
    def test_load_cache_from_file(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "token.json"
        cache_file.write_text('{"AccessToken": {}}')
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(cache_file),
        )
        cache = mgr._load_cache()
        assert cache is not None

    def test_load_cache_returns_empty_when_missing(self, tmp_path: Path) -> None:
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(tmp_path / "nonexistent.json"),
        )
        cache = mgr._load_cache()
        assert cache is not None

    def test_get_token_raises_when_no_accounts(self, tmp_path: Path) -> None:
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(tmp_path / "token.json"),
        )
        with patch.object(mgr, "_get_app") as mock_app:
            mock_app.return_value.get_accounts.return_value = []
            with pytest.raises(RuntimeError, match="Not authenticated"):
                mgr.get_token()

    def test_save_cache_writes_file(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "token.json"
        mgr = MicrosoftTokenManager(
            client_id="test_id",
            tenant_id="test_tenant",
            token_path=str(cache_file),
        )
        mock_cache = MagicMock()
        mock_cache.serialize.return_value = '{"cached": true}'
        mock_cache.has_state_changed = True
        mgr._cache = mock_cache
        mgr._save_cache()
        assert cache_file.exists()
        assert json.loads(cache_file.read_text()) == {"cached": True}
