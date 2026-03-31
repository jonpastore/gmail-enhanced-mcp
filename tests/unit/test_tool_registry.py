from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models import ToolCallParams
from src.tools import ToolRegistry


class TestToolRegistryIntegration:
    def test_all_14_tools_registered(self) -> None:
        mock_client = MagicMock()
        registry = ToolRegistry(gmail_client=mock_client)
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
        }
        assert tool_names == expected

    def test_all_tools_have_input_schema(self) -> None:
        mock_client = MagicMock()
        registry = ToolRegistry(gmail_client=mock_client)
        for tool in registry.list_tools():
            assert "inputSchema" in tool, f"{tool['name']} missing inputSchema"
            assert tool["inputSchema"]["type"] == "object"

    def test_execute_unknown_tool_raises(self) -> None:
        mock_client = MagicMock()
        registry = ToolRegistry(gmail_client=mock_client)
        with pytest.raises(ValueError, match="Unknown tool"):
            registry.execute_tool(ToolCallParams(name="fake_tool"))
