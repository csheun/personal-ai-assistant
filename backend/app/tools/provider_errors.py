from app.providers.errors import ProviderError
from app.tools.base import ToolFailure


def as_tool_failure(error: ProviderError) -> ToolFailure:
    """Maps a provider error to a tool failure with the same safe message."""
    code = {"not_found": "not_found", "timeout": "timeout"}.get(error.kind, "provider_error")
    return ToolFailure(code, error.message)  # type: ignore[arg-type]
