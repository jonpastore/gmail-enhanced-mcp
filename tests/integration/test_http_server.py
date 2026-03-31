from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestHealthEndpoint:
    def test_health_returns_ok(self) -> None:
        with patch("src.http_server.AccountRegistry") as mock_reg_cls:
            mock_reg = MagicMock()
            mock_reg.load_from_config = MagicMock()
            mock_reg_cls.return_value = mock_reg

            from src.http_server import create_app
            from starlette.testclient import TestClient

            cfg = MagicMock()
            cfg.mcp_auth_token = None
            app = create_app(cfg)
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
            assert resp.json()["version"] == "2.0.0"


class TestBearerAuth:
    def test_mcp_endpoint_rejects_without_token(self) -> None:
        with patch("src.http_server.AccountRegistry") as mock_reg_cls:
            mock_reg = MagicMock()
            mock_reg.load_from_config = MagicMock()
            mock_reg_cls.return_value = mock_reg

            from src.http_server import create_app
            from starlette.testclient import TestClient

            cfg = MagicMock()
            cfg.mcp_auth_token = "secret123"
            app = create_app(cfg)
            client = TestClient(app)

            resp = client.get("/mcp")
            assert resp.status_code == 401

    def test_mcp_endpoint_accepts_valid_token(self) -> None:
        with patch("src.http_server.AccountRegistry") as mock_reg_cls:
            mock_reg = MagicMock()
            mock_reg.load_from_config = MagicMock()
            mock_reg_cls.return_value = mock_reg

            from src.http_server import create_app
            from starlette.testclient import TestClient

            cfg = MagicMock()
            cfg.mcp_auth_token = "secret123"
            app = create_app(cfg)
            client = TestClient(app, raise_server_exceptions=False)

            resp = client.get(
                "/mcp",
                headers={"Authorization": "Bearer secret123"},
            )
            assert resp.status_code != 401

    def test_health_exempt_from_auth(self) -> None:
        with patch("src.http_server.AccountRegistry") as mock_reg_cls:
            mock_reg = MagicMock()
            mock_reg.load_from_config = MagicMock()
            mock_reg_cls.return_value = mock_reg

            from src.http_server import create_app
            from starlette.testclient import TestClient

            cfg = MagicMock()
            cfg.mcp_auth_token = "secret123"
            app = create_app(cfg)
            client = TestClient(app)

            resp = client.get("/health")
            assert resp.status_code == 200
