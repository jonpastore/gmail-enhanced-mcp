from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.account_registry import AccountRegistry
from src.models import ToolCallParams
from src.tools import ToolRegistry


def _make_registry() -> ToolRegistry:
    mock_client = MagicMock()
    mock_client.email_address = "test@gmail.com"
    mock_client.provider = "gmail"
    reg = AccountRegistry()
    reg.register("test@gmail.com", mock_client)
    return ToolRegistry(account_registry=reg)


class TestToolRegistryIntegration:
    def test_all_38_tools_registered(self) -> None:
        registry = _make_registry()
        tools = registry.list_tools()
        tool_names = {t["name"] for t in tools}
        expected = {
            "gmail_get_profile",
            "gmail_search_messages",
            "gmail_read_message",
            "gmail_read_thread",
            "gmail_download_attachment",
            "gmail_create_draft",
            "gmail_update_draft",
            "gmail_list_drafts",
            "gmail_send_draft",
            "gmail_send_email",
            "gmail_list_labels",
            "gmail_modify_thread_labels",
            "gmail_save_template",
            "gmail_use_template",
            "gmail_list_accounts",
            "gmail_triage_inbox",
            "gmail_add_priority_sender",
            "gmail_list_priority_senders",
            "gmail_remove_priority_sender",
            "gmail_track_followup",
            "gmail_check_followups",
            "gmail_reset_triage_cache",
            "gmail_trash_messages",
            "gmail_block_sender",
            "gmail_report_spam",
            "gmail_list_contacts",
            "gmail_import_contacts_as_priority",
            "gmail_get_unsubscribe_link",
            "gmail_create_label",
            "gmail_dismiss_contact",
            "gmail_list_dismissed_contacts",
            "gmail_check_email_conflicts",
            "gmail_meeting_prep",
            "gmail_today_briefing",
            "gmail_summarize_thread",
            "gmail_needs_reply",
            "gmail_batch_reply",
            "gmail_extract_itinerary",
        }
        assert tool_names == expected

    def test_all_tools_have_input_schema(self) -> None:
        registry = _make_registry()
        for tool in registry.list_tools():
            assert "inputSchema" in tool, f"{tool['name']} missing inputSchema"
            assert tool["inputSchema"]["type"] == "object"

    def test_execute_unknown_tool_raises(self) -> None:
        registry = _make_registry()
        with pytest.raises(ValueError, match="Unknown tool"):
            registry.execute_tool(ToolCallParams(name="fake_tool"))
