"""Simulated latency for mocked tools, applied when the registry is built.

Kept out of the tool handlers so swapping a mock for a real implementation in
Milestone 4 needs no latency code removed.
"""

import asyncio
import dataclasses
from typing import Any

from app.tools.base import Tool

# Base latency per mocked tool, in milliseconds (same as the frontend mock).
MOCK_LATENCY_MS: dict[str, int] = {
    "get_weather": 900,
    "calendar_list_events": 1300,
    "gmail_search": 1700,
    "web_search": 2100,
    "document_search": 1500,
    "summarize": 1200,
    "telegram_send_message": 700,
}


def with_latency(tool: Tool[Any, Any], seconds: float) -> Tool[Any, Any]:
    original = tool.handler

    async def delayed(args: Any) -> Any:
        await asyncio.sleep(seconds)
        return await original(args)

    return dataclasses.replace(tool, handler=delayed)
