from __future__ import annotations

from typing import Any


def text_content(text: str) -> dict[str, Any]:
    """Return MCP-format text content."""
    return {"content": [{"type": "text", "text": text}]}


def error_content(msg: str) -> dict[str, Any]:
    """Return MCP-format error content."""
    return {"content": [{"type": "text", "text": f"Error: {msg}"}], "isError": True}
