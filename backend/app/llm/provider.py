"""Builds a LangChain chat model from settings. The only module that knows which provider is used.

Everything else talks to `LLMClient` (llm/client.py), which wraps the `BaseChatModel` returned
here. Switching provider = LLM_PROVIDER + LLM_MODEL + that provider's key; no code changes.
Provider packages are imported lazily, so only the selected one has to be installed.
"""

from typing import TYPE_CHECKING, Any

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from app.config import Settings, StructuredOutputMethod

if TYPE_CHECKING:
    from app.llm.client import LLMClient


class LLMConfigError(RuntimeError):
    """Raised at startup when the LLM provider is misconfigured."""


_KEY_SETTING = {"groq": "groq_api_key", "openai": "openai_api_key", "anthropic": "anthropic_api_key"}

# json_schema makes the provider constrain output to the schema; it proved more reliable than
# function calling on Groq's gpt-oss, which sometimes answers with JSON text instead of a tool call.
_DEFAULT_STRUCTURED_OUTPUT: dict[str, StructuredOutputMethod] = {
    "groq": "json_schema",
    "openai": "json_schema",
    "anthropic": "function_calling",
}


def structured_output_method(settings: Settings) -> StructuredOutputMethod:
    return settings.llm_structured_output or _DEFAULT_STRUCTURED_OUTPUT[settings.llm_provider]


def build_chat_model(settings: Settings) -> BaseChatModel:
    provider = settings.llm_provider
    key_name = _KEY_SETTING[provider]
    secret: SecretStr | None = getattr(settings, key_name)
    api_key = secret.get_secret_value() if secret else None

    # A local OpenAI-compatible server (e.g. Ollama) may not need a key; hosted providers always do.
    if not api_key and not (provider == "openai" and settings.llm_base_url):
        raise LLMConfigError(f"{key_name.upper()} is required when LLM_PROVIDER={provider}. Set it in backend/.env.")

    common: dict[str, Any] = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
        "max_tokens": settings.llm_max_tokens,
    }

    try:
        if provider == "groq":
            from langchain_groq import ChatGroq

            return ChatGroq(api_key=api_key, **common)
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(api_key=api_key or "not-needed", base_url=settings.llm_base_url, **common)
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(api_key=api_key, **common)
    except ImportError as exc:
        raise LLMConfigError(f"Provider '{provider}' is not installed. Run: pip install -e '.[{provider}]'") from exc

    raise LLMConfigError(f"Unsupported LLM_PROVIDER '{provider}'")


def build_llm_client(settings: Settings) -> "LLMClient":
    """The configured LLMClient: provider model + timeout + structured-output mode."""
    from app.llm.client import LLMClient

    return LLMClient(
        build_chat_model(settings),
        provider=settings.llm_provider,
        model_name=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        structured_method=structured_output_method(settings),
    )
