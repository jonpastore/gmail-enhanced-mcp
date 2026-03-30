from __future__ import annotations

from typing import Any

from loguru import logger

from ..models import ToolCallParams


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Any] = {}

    def register(
        self, name: str, description: str, input_schema: dict[str, Any], handler: Any
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        self._handlers[name] = handler

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    def execute_tool(self, params: ToolCallParams) -> dict[str, Any]:
        handler = self._handlers.get(params.name)
        if handler is None:
            raise ValueError(f"Unknown tool: {params.name}")
        logger.info(f"Executing tool: {params.name}")
        result = handler(params.arguments)
        return result
