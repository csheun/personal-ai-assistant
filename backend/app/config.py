"""Application settings, loaded from environment variables (and `.env` in dev).

Everything configurable lives here so the rest of the code never reads
`os.environ` directly. Secrets are typed as `SecretStr` so they are masked in
logs, reprs and tracebacks.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["groq", "openai", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Personal AI Assistant"
    log_level: str = "INFO"

    # --- LLM ---
    llm_provider: LLMProvider = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: SecretStr | None = None
    # Optional: point the OpenAI provider at any OpenAI-compatible server (Ollama, vLLM, ...).
    llm_base_url: str | None = None
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)

    # --- Agent ---
    # Max LLM<->tool round trips per request; protects against runaway loops.
    agent_max_iterations: int = Field(default=5, ge=1, le=20)
    tool_timeout_seconds: float = Field(default=10.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
