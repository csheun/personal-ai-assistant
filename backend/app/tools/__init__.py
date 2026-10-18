from app.tools.base import Tool, ToolError, ToolInput, ToolRegistry, ToolResult
from app.tools.weather import weather_tool
from app.tools.web_search import web_search_tool


def build_default_registry(timeout_seconds: float = 10.0) -> ToolRegistry:
    """The explicit allow-list of tools the LLM may request."""
    registry = ToolRegistry(timeout_seconds=timeout_seconds)
    registry.register(weather_tool)
    registry.register(web_search_tool)
    return registry


__all__ = ["Tool", "ToolError", "ToolInput", "ToolRegistry", "ToolResult", "build_default_registry"]
