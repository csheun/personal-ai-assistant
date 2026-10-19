import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.llm.client import LLMClient, LLMOutputError, LLMUnavailable
from tests.fakes import RaisingChatModel, SlowChatModel, fake_llm, structured


class Answer(BaseModel):
    text: str


async def test_structured_output_is_validated_and_usage_recorded() -> None:
    llm, _ = fake_llm(structured("Answer", {"text": "hi"}, tokens=(42, 7)))
    value, usage = await llm.structured([HumanMessage("x")], Answer, purpose="test")
    assert value == Answer(text="hi")
    assert (usage.purpose, usage.provider, usage.model) == ("test", "fake", "fake-model")
    assert (usage.input_tokens, usage.output_tokens) == (42, 7)
    assert usage.duration_ms >= 0


async def test_output_not_matching_schema_is_an_output_error() -> None:
    llm, _ = fake_llm(structured("Answer", {"wrong": 1}))
    with pytest.raises(LLMOutputError):
        await llm.structured([HumanMessage("x")], Answer, purpose="test")


async def test_no_structured_output_at_all_is_an_output_error() -> None:
    llm, _ = fake_llm(AIMessage("I refuse to use the tool."))
    with pytest.raises(LLMOutputError):
        await llm.structured([HumanMessage("x")], Answer, purpose="test")


async def test_timeout_becomes_unavailable() -> None:
    model = SlowChatModel(responses=[AIMessage("late")], delay=1.0)
    llm = LLMClient(model, provider="fake", model_name="m", timeout_seconds=0.05)
    with pytest.raises(LLMUnavailable, match="too long"):
        await llm.text([HumanMessage("x")], purpose="test")


class RateLimitError(Exception):
    status_code = 429


class AuthenticationError(Exception):
    pass


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (RateLimitError("secret request details"), "busy"),
        (AuthenticationError("key gsk_123 invalid"), "credentials"),
        (RuntimeError("boom"), "request failed"),
    ],
)
async def test_provider_errors_become_safe_messages(error: Exception, message: str) -> None:
    llm = LLMClient(RaisingChatModel(responses=[], error=error), provider="fake", model_name="m", timeout_seconds=5)
    with pytest.raises(LLMUnavailable, match=message) as caught:
        await llm.text([HumanMessage("x")], purpose="test")
    assert "gsk_" not in str(caught.value) and "secret" not in str(caught.value)


async def test_text_call() -> None:
    llm, _ = fake_llm(AIMessage("plain", usage_metadata={"input_tokens": 3, "output_tokens": 1, "total_tokens": 4}))
    text, usage = await llm.text([HumanMessage("x")], purpose="chat")
    assert text == "plain" and usage.output_tokens == 1


class BadRequestError(Exception):
    status_code = 400

    def __init__(self, code: str) -> None:
        super().__init__("400")
        self.body = {"error": {"code": code, "failed_generation": "{...}"}}


async def test_provider_rejecting_the_models_output_is_an_output_error_not_an_outage() -> None:
    llm = LLMClient(RaisingChatModel(responses=[], error=BadRequestError("tool_use_failed")), provider="groq", model_name="m", timeout_seconds=5)
    with pytest.raises(LLMOutputError):
        await llm.structured([HumanMessage("x")], Answer, purpose="plan")
