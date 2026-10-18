"""A deterministic stand-in for a real chat model, so agent tests need no network or API key."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    """Returns `responses` in order, and records what it was sent."""

    responses: list[AIMessage]
    received: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        self.bound_tools = list(tools)
        return self

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        self.received.append(list(messages))
        if len(self.received) > len(self.responses):
            raise RuntimeError("ScriptedChatModel ran out of responses")
        return ChatResult(generations=[ChatGeneration(message=self.responses[len(self.received) - 1])])


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}
