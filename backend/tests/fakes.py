"""Deterministic stand-ins for a real chat model, so LLM tests need no network or API key."""

import asyncio
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.llm.client import LLMClient


class ScriptedChatModel(BaseChatModel):
    """Returns `responses` in order, and records what it was sent."""

    responses: list[AIMessage]
    received: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[Any] = Field(default_factory=list)

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


class SlowChatModel(ScriptedChatModel):
    delay: float = 1.0

    async def _agenerate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        await asyncio.sleep(self.delay)
        return self._generate(messages)


class RaisingChatModel(ScriptedChatModel):
    error: Exception

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        raise self.error


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def structured(schema_name: str, args: dict[str, Any], tokens: tuple[int, int] = (100, 20)) -> AIMessage:
    """What a provider returns for a structured-output call: one tool call named after the schema."""
    return AIMessage(
        "",
        tool_calls=[tool_call(schema_name, args)],
        usage_metadata={"input_tokens": tokens[0], "output_tokens": tokens[1], "total_tokens": sum(tokens)},
    )


def fake_llm(*responses: AIMessage, timeout: float = 5.0) -> tuple[LLMClient, ScriptedChatModel]:
    model = ScriptedChatModel(responses=list(responses))
    return LLMClient(model, provider="fake", model_name="fake-model", timeout_seconds=timeout), model
