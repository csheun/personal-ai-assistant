"""Tool registry: the only path by which LLM output can cause Python code to run.

Safety model
------------
The LLM never executes anything. It can only *ask* for a tool by name with a
JSON blob of arguments. The registry then:

1. looks the name up in an explicit allow-list (unknown names are rejected),
2. validates the arguments against the tool's Pydantic input model,
3. runs the tool's handler with a timeout,
4. validates the handler's return value against the output model,
5. converts every failure into a structured `ToolResult` instead of raising,
   so one bad tool call can't crash the request and the LLM can see what
   went wrong and recover.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True)
class ActionPreview:
    """What the user is asked to approve before an external_write tool runs."""

    action: str  # e.g. "Send a Telegram message to Me"
    destination: str  # e.g. "Telegram · Me"
    body: str  # exactly what will be sent


class ToolInput(BaseModel):
    """Base for tool inputs. Unknown fields are rejected rather than silently dropped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


@dataclass(frozen=True)
class Tool(Generic[InputT, OutputT]):
    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]
    handler: Callable[[InputT], Awaitable[OutputT]]
    mocked: bool = False
    # "read": only fetches data. "external_write": acts on the outside world (sends, posts).
    # Workflows always require the user's approval before running an external_write tool.
    risk: Literal["read", "external_write"] = "read"
    # Input fields the backend fills from upstream task results at run time. The LLM planner
    # never sees or sets them, so it can't invent data it hasn't fetched yet.
    bound_inputs: frozenset[str] = frozenset()
    # external_write tools describe the action for the approval card, from validated input.
    describe_action: Callable[[InputT], ActionPreview] | None = None

    @property
    def side_effects(self) -> bool:
        return self.risk == "external_write"

    def to_llm_schema(self) -> dict[str, Any]:
        """OpenAI-style function schema; LangChain converts it for any provider."""
        description = f"[MOCKED DATA] {self.description}" if self.mocked else self.description
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": description,
                "parameters": self.input_model.model_json_schema(),
            },
        }


ToolErrorCode = Literal["unknown_tool", "invalid_arguments", "execution_failed", "timeout", "simulated_failure"]


class ToolError(BaseModel):
    code: ToolErrorCode
    message: str
    details: list[dict[str, Any]] | None = None


class ToolResult(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    ok: bool
    output: dict[str, Any] | None = None
    error: ToolError | None = None
    mocked: bool = False


class ToolRegistry:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._tools: dict[str, Tool[Any, Any]] = {}
        self._timeout_seconds = timeout_seconds

    def register(self, tool: Tool[Any, Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any, Any] | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def filtered(self, keep: Callable[[Tool[Any, Any]], bool]) -> "ToolRegistry":
        """A new registry containing only the tools `keep` accepts."""
        subset = ToolRegistry(timeout_seconds=self._timeout_seconds)
        for tool in self._tools.values():
            if keep(tool):
                subset.register(tool)
        return subset

    def llm_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_llm_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                arguments=arguments,
                ok=False,
                error=ToolError(code="unknown_tool", message=f"No tool named '{name}'. Available: {self.names}"),
            )

        def failure(error: ToolError) -> ToolResult:
            return ToolResult(tool_name=name, arguments=arguments, ok=False, error=error, mocked=tool.mocked)

        try:
            parsed = tool.input_model.model_validate(arguments)
        except ValidationError as exc:
            return failure(
                ToolError(
                    code="invalid_arguments",
                    message="Arguments did not match the tool's input schema.",
                    # include_url/include_context/include_input off: keep the payload small and JSON-safe.
                    details=exc.errors(include_url=False, include_context=False, include_input=False),
                )
            )

        try:
            raw_output = await asyncio.wait_for(tool.handler(parsed), timeout=self._timeout_seconds)
            output = tool.output_model.model_validate(raw_output)
        except TimeoutError:
            return failure(ToolError(code="timeout", message=f"Tool timed out after {self._timeout_seconds}s."))
        except Exception:
            # Log the real error server-side; don't leak internals (paths, keys, stack traces) to the LLM/client.
            logger.exception("Tool '%s' failed", name)
            return failure(ToolError(code="execution_failed", message="The tool failed while running."))

        return ToolResult(
            tool_name=name,
            arguments=parsed.model_dump(mode="json"),
            ok=True,
            output=output.model_dump(mode="json"),
            mocked=tool.mocked,
        )
