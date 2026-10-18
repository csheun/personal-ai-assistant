import pytest

from app.config import Settings
from app.llm.provider import LLMConfigError, build_chat_model


def settings(**overrides: object) -> Settings:
    base = {"groq_api_key": None, "openai_api_key": None, "anthropic_api_key": None}
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def test_groq_model_is_built_with_limits_from_settings() -> None:
    model = build_chat_model(settings(llm_provider="groq", groq_api_key="test-key", llm_max_tokens=512, llm_max_retries=0))
    assert type(model).__name__ == "ChatGroq"
    assert model.max_tokens == 512 and model.max_retries == 0


def test_missing_key_names_the_right_variable() -> None:
    with pytest.raises(LLMConfigError, match="GROQ_API_KEY"):
        build_chat_model(settings(llm_provider="groq"))
    with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
        build_chat_model(settings(llm_provider="anthropic"))


def test_other_providers_keys_are_ignored() -> None:
    with pytest.raises(LLMConfigError, match="GROQ_API_KEY"):
        build_chat_model(settings(llm_provider="groq", openai_api_key="sk-other"))


def test_uninstalled_provider_explains_how_to_install() -> None:
    try:
        import langchain_anthropic  # noqa: F401

        pytest.skip("langchain-anthropic is installed")
    except ImportError:
        pass
    with pytest.raises(LLMConfigError, match=r"pip install -e '\.\[anthropic\]'"):
        build_chat_model(settings(llm_provider="anthropic", anthropic_api_key="test"))


def test_structured_output_method_defaults_per_provider_and_can_be_overridden() -> None:
    from app.llm.provider import structured_output_method

    assert structured_output_method(settings(llm_provider="groq")) == "json_schema"
    assert structured_output_method(settings(llm_provider="anthropic")) == "function_calling"
    assert structured_output_method(settings(llm_provider="groq", llm_structured_output="function_calling")) == "function_calling"
