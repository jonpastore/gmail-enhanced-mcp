"""Integration tests for triage tools via ToolRegistry.execute_tool."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.models import ToolCallParams
from src.tools import ToolRegistry


def _make_registry() -> tuple[ToolRegistry, MagicMock]:
    mock_client = MagicMock()
    mock_client.email_address = "test@gmail.com"
    mock_client.search_messages.return_value = {
        "messages": [{"id": "m1", "threadId": "t1"}],
    }
    mock_client.read_message.return_value = {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "test@gmail.com"},
                {"name": "Subject", "value": "Test"},
                {"name": "Date", "value": "Mon, 10 Mar 2026 10:00:00 -0500"},
            ],
            "body": {"data": ""},
            "parts": [],
        },
    }

    mock_reg = MagicMock()
    mock_reg.get.return_value = mock_client

    registry = ToolRegistry(account_registry=mock_reg, cache_db_path=":memory:")
    return registry, mock_client


class TestTriageToolsInRegistry:
    def test_triage_tools_appear_in_list(self) -> None:
        registry, _ = _make_registry()
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        assert "gmail_triage_inbox" in names
        assert "gmail_add_priority_sender" in names
        assert "gmail_list_priority_senders" in names
        assert "gmail_remove_priority_sender" in names
        assert "gmail_track_followup" in names
        assert "gmail_check_followups" in names
        assert "gmail_reset_triage_cache" in names

    def test_total_tool_count_is_22(self) -> None:
        registry, _ = _make_registry()
        tools = registry.list_tools()
        assert len(tools) == 28

    def test_triage_inbox_via_execute(self) -> None:
        registry, _ = _make_registry()
        params = ToolCallParams(name="gmail_triage_inbox", arguments={})
        result = registry.execute_tool(params)
        assert not result.get("isError")
        assert "m1" in result["content"][0]["text"]

    def test_add_then_list_priority_sender_roundtrip(self) -> None:
        registry, _ = _make_registry()

        add_params = ToolCallParams(
            name="gmail_add_priority_sender",
            arguments={"pattern": "*@test.gov", "tier": "critical", "label": "Test Gov"},
        )
        add_result = registry.execute_tool(add_params)
        assert not add_result.get("isError")

        list_params = ToolCallParams(
            name="gmail_list_priority_senders",
            arguments={},
        )
        list_result = registry.execute_tool(list_params)
        assert "*@test.gov" in list_result["content"][0]["text"]

    def test_reset_triage_cache_via_execute(self) -> None:
        registry, _ = _make_registry()
        params = ToolCallParams(
            name="gmail_reset_triage_cache",
            arguments={"confirm": True},
        )
        result = registry.execute_tool(params)
        assert not result.get("isError")
        assert "reset" in result["content"][0]["text"].lower()

    def test_track_followup_via_execute(self) -> None:
        registry, _ = _make_registry()
        params = ToolCallParams(
            name="gmail_track_followup",
            arguments={"messageId": "m1"},
        )
        result = registry.execute_tool(params)
        assert not result.get("isError")

    def test_check_followups_via_execute(self) -> None:
        registry, _ = _make_registry()
        params = ToolCallParams(
            name="gmail_check_followups",
            arguments={},
        )
        result = registry.execute_tool(params)
        assert not result.get("isError")
        assert "Follow-Up Report" in result["content"][0]["text"]

    def test_triage_tools_have_account_property(self) -> None:
        registry, _ = _make_registry()
        tools = registry.list_tools()
        triage_names = {
            "gmail_triage_inbox",
            "gmail_add_priority_sender",
            "gmail_list_priority_senders",
            "gmail_remove_priority_sender",
            "gmail_track_followup",
            "gmail_check_followups",
            "gmail_reset_triage_cache",
        }
        for tool in tools:
            if tool["name"] in triage_names:
                assert (
                    "account" in tool["inputSchema"]["properties"]
                ), f"{tool['name']} missing account property"

    def test_close_cleans_up_cache(self) -> None:
        registry, _ = _make_registry()
        registry.close()
