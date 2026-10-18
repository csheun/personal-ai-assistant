"""Application settings, loaded from environment variables (and `.env` in dev).

Everything configurable lives here so the rest of the code never reads
`os.environ` directly. Secrets are typed as `SecretStr` so they are masked in
logs, reprs and tracebacks.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["groq", "openai", "anthropic"]
StructuredOutputMethod = Literal["json_schema", "function_calling", "json_mode"]

# Anchor to backend/.env so the app finds it regardless of the directory it is started from.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Personal AI Assistant"
    log_level: str = "INFO"

    # --- Mode ---
    # true: keyword planner + simulated tools (no keys needed). false: real LLM and providers.
    mock_mode: bool = True

    # --- LLM (used when MOCK_MODE=false) ---
    llm_provider: LLMProvider = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    # One key per provider, so switching is just LLM_PROVIDER + LLM_MODEL. Only the selected one is required.
    groq_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    # Optional: point the OpenAI provider at any OpenAI-compatible server (Ollama, vLLM, ...).
    llm_base_url: str | None = None
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    # Hard limit per LLM call, including the provider's own retries.
    llm_timeout_seconds: float = Field(default=45.0, gt=0)
    # Cap on generated tokens per call (cost and runaway-output protection).
    llm_max_tokens: int = Field(default=2048, ge=64, le=16_384)
    # Provider-level retries for transient errors (rate limits, 5xx). Kept low: each retry adds latency.
    llm_max_retries: int = Field(default=1, ge=0, le=5)
    # How structured output is requested. Unset = the provider's most reliable mode
    # (json_schema for groq/openai, function_calling for anthropic).
    llm_structured_output: StructuredOutputMethod | None = None
    # Planner: total LLM attempts per request (1 draft + repairs after validation errors).
    planner_max_attempts: int = Field(default=2, ge=1, le=4)

    tool_timeout_seconds: float = Field(default=10.0, gt=0)

    # --- Workflows (Milestone 3: all tools mocked) ---
    # Multiplies each mocked tool's simulated latency. 0 = instant, 1 = realistic demo pacing.
    mock_latency_scale: float = Field(default=1.0, ge=0, le=10)
    # Browser origins allowed to call the API (the Next.js dev server by default).
    cors_origins: list[str] = ["http://localhost:3000"]
    # Comment lines sent on idle SSE streams so proxies don't close them.
    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
