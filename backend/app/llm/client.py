"""LLMClient: the single doorway to the language model.

Everything that talks to the LLM (planner, synthesizer) goes through here, which gives one place for:
- a hard timeout per call (on top of the provider's own),
- usage metadata (model, latency, tokens) recorded on every call,
- translating provider-specific exceptions into two domain errors the rest of the app understands.
"""

import asyncio
import logging
import time
from collections.abc import Sequence
from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMUsage(BaseModel):
    """What one LLM call cost. Token counts are None when the provider doesn't report them."""

    purpose: str
    provider: str
    model: str
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMUnavailable(Exception):
    """The LLM couldn't be reached or refused the request (timeout, rate limit, auth, outage)."""


class LLMOutputError(Exception):
    """The LLM answered, but not in the required structure."""


class LLMClient:
    def __init__(
        self,
        model: BaseChatModel,
        *,
        provider: str,
        model_name: str,
        timeout_seconds: float,
        structured_method: str | None = None,
    ) -> None:
        self._model = model
        self.provider = provider
        self.model_name = model_name
        self._timeout = timeout_seconds
        self._structured_method = structured_method

    async def structured(self, messages: Sequence[BaseMessage], schema: type[T], *, purpose: str) -> tuple[T, LLMUsage]:
        """Asks for output matching `schema` (via the provider's tool/JSON mode) and validates it with Pydantic."""
        options = {"method": self._structured_method} if self._structured_method else {}
        runnable = self._model.with_structured_output(schema, include_raw=True, **options)
        result, usage = await self._call(runnable.ainvoke(list(messages)), purpose)
        if not isinstance(result, dict):  # pragma: no cover - defensive
            raise LLMOutputError("Unexpected structured-output response.")
        usage = _with_tokens(usage, result.get("raw"))
        if result.get("parsing_error") is not None or not isinstance(result.get("parsed"), schema):
            raise LLMOutputError(str(result.get("parsing_error") or "The model did not return the required structure."))
        return result["parsed"], usage

    async def text(self, messages: Sequence[BaseMessage], *, purpose: str) -> tuple[str, LLMUsage]:
        message, usage = await self._call(self._model.ainvoke(list(messages)), purpose)
        return message.text, _with_tokens(usage, message)

    async def _call(self, coroutine, purpose: str):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(coroutine, timeout=self._timeout)
        except TimeoutError as exc:
            raise LLMUnavailable("The AI service took too long to respond. Try again.") from exc
        except Exception as exc:
            if _is_rejected_generation(exc):
                # The provider refused the model's own output (didn't fit the schema): a bad answer,
                # not an outage, so callers like the planner can repair instead of failing.
                raise LLMOutputError("The model's output didn't match the required format.") from exc
            logger.exception("LLM call failed (%s)", purpose)
            raise LLMUnavailable(_describe(exc)) from exc
        usage = LLMUsage(
            purpose=purpose,
            provider=self.provider,
            model=self.model_name,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        logger.info("LLM %s: %s/%s %dms", purpose, self.provider, self.model_name, usage.duration_ms)
        return result, usage


def _with_tokens(usage: LLMUsage, message: object) -> LLMUsage:
    metadata = getattr(message, "usage_metadata", None) if isinstance(message, AIMessage) else None
    if not metadata:
        return usage
    return usage.model_copy(update={"input_tokens": metadata.get("input_tokens"), "output_tokens": metadata.get("output_tokens")})


_REJECTED_GENERATION_CODES = {"tool_use_failed", "json_validate_failed"}


def _is_rejected_generation(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else None
    return isinstance(error, dict) and error.get("code") in _REJECTED_GENERATION_CODES


def _describe(exc: Exception) -> str:
    """User-safe description. Provider exceptions can contain request details, so never echo them."""
    name = type(exc).__name__.lower()
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429 or "ratelimit" in name:
        return "The AI service is busy (rate limited). Try again in a moment."
    if status in (401, 403) or "authentication" in name or "permission" in name:
        return "The AI service rejected the server's credentials. Check the API key in backend/.env."
    if "timeout" in name:
        return "The AI service took too long to respond. Try again."
    return "The AI service request failed. Try again."
