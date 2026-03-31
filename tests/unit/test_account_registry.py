from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.account_registry import AccountRegistry


def _mock_client(email: str, provider: str) -> MagicMock:
    client = MagicMock()
    client.email_address = email
    client.provider = provider
    return client


class TestAccountRegistry:
    def test_register_and_get(self) -> None:
        reg = AccountRegistry()
        client = _mock_client("test@gmail.com", "gmail")
        reg.register("test@gmail.com", client)
        assert reg.get("test@gmail.com") is client

    def test_get_default(self) -> None:
        reg = AccountRegistry()
        client = _mock_client("test@gmail.com", "gmail")
        reg.register("test@gmail.com", client, default=True)
        assert reg.get() is client

    def test_first_registered_is_default(self) -> None:
        reg = AccountRegistry()
        c1 = _mock_client("a@gmail.com", "gmail")
        c2 = _mock_client("b@outlook.com", "outlook")
        reg.register("a@gmail.com", c1)
        reg.register("b@outlook.com", c2)
        assert reg.get() is c1

    def test_get_unknown_raises(self) -> None:
        reg = AccountRegistry()
        with pytest.raises(ValueError, match="Unknown account"):
            reg.get("nonexistent@test.com")

    def test_get_no_accounts_raises(self) -> None:
        reg = AccountRegistry()
        with pytest.raises(ValueError, match="No accounts registered"):
            reg.get()

    def test_list_accounts(self) -> None:
        reg = AccountRegistry()
        reg.register("a@gmail.com", _mock_client("a@gmail.com", "gmail"))
        reg.register("b@outlook.com", _mock_client("b@outlook.com", "outlook"))
        accounts = reg.list_accounts()
        assert len(accounts) == 2
        assert accounts[0]["email"] == "a@gmail.com"
        assert accounts[0]["provider"] == "gmail"
        assert accounts[0]["default"] is True
        assert accounts[1]["default"] is False

    def test_multiple_gmail_accounts(self) -> None:
        reg = AccountRegistry()
        reg.register("personal@gmail.com", _mock_client("personal@gmail.com", "gmail"))
        reg.register("work@company.com", _mock_client("work@company.com", "gmail"))
        assert reg.get("work@company.com").email_address == "work@company.com"
