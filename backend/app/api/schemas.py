"""HTTP request/response contracts. These are the public API; keep them stable for the frontend."""

from pydantic import BaseModel, ConfigDict, Field

from app.tools import ToolResult


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000, examples=["What's the weather in Singapore?"])


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolResult] = Field(description="Every tool the agent executed, in order, with validated inputs.")
    iterations: int = Field(description="Number of LLM calls made.")
    model: str
