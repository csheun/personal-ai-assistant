"""The tool registry for MOCK_MODE=false: real providers, the LLM synthesizer.

Only tools whose configuration is present are registered, so the planner never sees a tool
that can't run (e.g. no WEB_SEARCH_API_KEY → no web_search).
"""

import logging

import httpx

from app.config import Settings
from app.llm.client import LLMClient
from app.providers.open_meteo import OpenMeteoClient
from app.providers.tavily import TavilyClient
from app.providers.telegram import TelegramClient
from app.tools.base import ToolRegistry
from app.tools.summarize import make_llm_summarize_tool
from app.tools.telegram import make_telegram_tool, telegram_tool
from app.tools.weather import make_weather_tool
from app.tools.web_search import make_web_search_tool

logger = logging.getLogger(__name__)

# The tool's own limit sits a little above the HTTP timeout, so the provider's clearer error wins.
_GRACE_SECONDS = 2.0


def build_live_registry(settings: Settings, http: httpx.AsyncClient, llm: LLMClient) -> ToolRegistry:
    registry = ToolRegistry(timeout_seconds=settings.tool_timeout_seconds)

    registry.register(
        make_weather_tool(
            OpenMeteoClient(http, timeout_seconds=settings.weather_timeout_seconds),
            timeout_seconds=settings.weather_timeout_seconds * 2 + _GRACE_SECONDS,  # geocode + forecast
        )
    )

    if settings.web_search_api_key:
        client = TavilyClient(
            http, settings.web_search_api_key.get_secret_value(), timeout_seconds=settings.web_search_timeout_seconds
        )
        registry.register(make_web_search_tool(client, timeout_seconds=settings.web_search_timeout_seconds + _GRACE_SECONDS))
    else:
        logger.warning("WEB_SEARCH_API_KEY is not set: web search is disabled.")

    registry.register(make_llm_summarize_tool(llm, timeout_seconds=settings.llm_timeout_seconds + _GRACE_SECONDS))

    if settings.telegram_bot_token and settings.telegram_chat_id:
        client = TelegramClient(
            http, settings.telegram_bot_token.get_secret_value(), timeout_seconds=settings.telegram_timeout_seconds
        )
        registry.register(
            make_telegram_tool(
                client,
                chat_id=settings.telegram_chat_id,
                label=settings.telegram_chat_label,
                timeout_seconds=settings.telegram_timeout_seconds + _GRACE_SECONDS,
            )
        )
    else:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set: Telegram sending is simulated.")
        registry.register(telegram_tool)
    return registry
