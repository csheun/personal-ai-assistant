from app.tools.base import Tool, ToolError, ToolInput, ToolRegistry, ToolResult
from app.tools.calendar import calendar_tool
from app.tools.documents import document_tool
from app.tools.gmail import gmail_tool
from app.tools.latency import MOCK_LATENCY_MS, with_latency
from app.tools.summarize import summarize_tool
from app.tools.telegram import telegram_tool
from app.tools.weather import weather_tool
from app.tools.web_search import web_search_tool

# Every tool is mocked in this milestone. Milestone 4 swaps entries for real implementations.
ALL_TOOLS = [weather_tool, web_search_tool, calendar_tool, gmail_tool, document_tool, summarize_tool, telegram_tool]


def build_default_registry(timeout_seconds: float = 10.0, mock_latency_scale: float = 0.0) -> ToolRegistry:
    """The explicit allow-list of tools.

    `mock_latency_scale` multiplies each mocked tool's simulated latency
    (0 = instant, for unit tests; 1 = realistic, for the demo).
    """
    registry = ToolRegistry(timeout_seconds=timeout_seconds)
    for tool in ALL_TOOLS:
        if tool.mocked and mock_latency_scale > 0:
            tool = with_latency(tool, MOCK_LATENCY_MS.get(tool.name, 0) / 1000 * mock_latency_scale)
        registry.register(tool)
    return registry


__all__ = ["Tool", "ToolError", "ToolInput", "ToolRegistry", "ToolResult", "build_default_registry"]
