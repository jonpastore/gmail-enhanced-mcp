from __future__ import annotations

from unittest.mock import MagicMock

from src.account_registry import AccountRegistry
from src.models import ToolCallParams
from src.tools import ToolRegistry


def _mock_client(email: str, provider: str) -> MagicMock:
    client = MagicMock()
    client.email_address = email
    client.provider = provider
    client.get_profile.return_value = {"emailAddress": email}
    return client


class TestMultiAccountRouting:
    def test_default_account_used_when_no_account_param(self) -> None:
        reg = AccountRegistry()
        gmail = _mock_client("personal@gmail.com", "gmail")
        reg.register("personal@gmail.com", gmail)
        registry = ToolRegistry(account_registry=reg)
        registry.execute_tool(ToolCallParams(name="gmail_get_profile", arguments={}))
        gmail.get_profile.assert_called_once()

    def test_explicit_account_routes_correctly(self) -> None:
        reg = AccountRegistry()
        gmail = _mock_client("personal@gmail.com", "gmail")
        outlook = _mock_client("work@company.com", "outlook")
        reg.register("personal@gmail.com", gmail)
        reg.register("work@company.com", outlook)
        registry = ToolRegistry(account_registry=reg)
        registry.execute_tool(
            ToolCallParams(
                name="gmail_get_profile",
                arguments={"account": "work@company.com"},
            )
        )
        outlook.get_profile.assert_called_once()
        gmail.get_profile.assert_not_called()

    def test_list_accounts_tool(self) -> None:
        reg = AccountRegistry()
        reg.register("a@gmail.com", _mock_client("a@gmail.com", "gmail"))
        reg.register("b@outlook.com", _mock_client("b@outlook.com", "outlook"))
        registry = ToolRegistry(account_registry=reg)
        result = registry.execute_tool(
            ToolCallParams(
                name="gmail_list_accounts",
                arguments={},
            )
        )
        text = result["content"][0]["text"]
        assert "a@gmail.com" in text
        assert "b@outlook.com" in text

    def test_account_param_in_tool_schemas(self) -> None:
        reg = AccountRegistry()
        reg.register("a@gmail.com", _mock_client("a@gmail.com", "gmail"))
        registry = ToolRegistry(account_registry=reg)
        tools = registry.list_tools()
        for tool in tools:
            if tool["name"] != "gmail_list_accounts":
                props = tool["inputSchema"].get("properties", {})
                assert "account" in props, f"{tool['name']} missing account param"
