"""Builds a LangChain chat model from settings.

The rest of the app depends only on LangChain's `BaseChatModel` interface, so
switching provider is an env-var change. Provider packages are imported lazily
so you only need to install the one you use.
"""

from langchain_core.language_models import BaseChatModel

from app.config import Settings


class LLMConfigError(RuntimeError):
    """Raised at startup when the LLM provider is misconfigured."""


def build_chat_model(settings: Settings) -> BaseChatModel:
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    provider = settings.llm_provider

    # A local OpenAI-compatible server (e.g. Ollama) may not need a key; hosted providers always do.
    if api_key is None and not (provider == "openai" and settings.llm_base_url):
        raise LLMConfigError(f"LLM_API_KEY is required for provider '{provider}'. Set it in backend/.env.")

    common = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": 2,
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
        raise LLMConfigError(
            f"Provider '{provider}' is not installed. Run: pip install -e '.[{provider}]'"
        ) from exc

    raise LLMConfigError(f"Unsupported LLM_PROVIDER '{provider}'")
