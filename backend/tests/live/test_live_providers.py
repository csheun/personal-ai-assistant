"""Optional live checks against the real providers. Skipped unless LIVE_TESTS=1.

    LIVE_TESTS=1 pytest -m live -v                          # LLM, weather, search (read-only)
    LIVE_TESTS=1 LIVE_TELEGRAM=1 pytest -m live -v          # also sends ONE real Telegram message

Uses backend/.env. Each test skips itself if the key it needs is missing. These cost
real API quota (a few thousand Groq tokens, a couple of Tavily searches).
"""

import os
from datetime import date, timedelta

import httpx
import pytest

from app.config import Settings
from app.llm.provider import build_llm_client
from app.providers.open_meteo import OpenMeteoClient
from app.providers.tavily import TavilyClient
from app.providers.telegram import TelegramClient
from app.tools.live import build_live_registry
from app.workflows.llm_planner import LLMPlanner
from app.workflows.plans import DirectReply, Plan

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("LIVE_TESTS"), reason="live tests are opt-in: set LIVE_TESTS=1"),
]

TOMORROW = date.today() + timedelta(days=1)


@pytest.fixture
def settings() -> Settings:
    return Settings(mock_mode=False)


async def test_open_meteo_forecast() -> None:
    async with httpx.AsyncClient() as http:
        client = OpenMeteoClient(http)
        place = await client.geocode("Singapore")
        data = await client.forecast(place, start=TOMORROW, end=TOMORROW)
    assert place.country == "Singapore"
    assert data["daily"]["time"] == [TOMORROW.isoformat()]


async def test_tavily_search(settings: Settings) -> None:
    if not settings.web_search_api_key:
        pytest.skip("WEB_SEARCH_API_KEY not set")
    async with httpx.AsyncClient() as http:
        hits = await TavilyClient(http, settings.web_search_api_key.get_secret_value()).search(
            "artificial intelligence", max_results=3, topic="news", time_range="week"
        )
    assert hits and all(h.url.startswith("http") for h in hits)


async def test_llm_plans_the_demo_request_and_answers_general_questions(settings: Settings) -> None:
    async with httpx.AsyncClient() as http:
        llm = build_llm_client(settings)
        planner = LLMPlanner(llm, build_live_registry(settings, http, llm), max_attempts=settings.planner_max_attempts)
        plan = await planner.plan(
            "Check tomorrow's weather in Singapore, search for recent AI news, summarize both, and send the summary to Telegram.",
            today=date.today(),
        )
        answer = await planner.plan("In one sentence, what is a DAG?", today=date.today())
    assert isinstance(plan, Plan)
    tools = [t.tool_name for t in plan.tasks]
    assert {"get_weather", "summarize", "telegram_send_message"} <= set(tools)
    assert next(t for t in plan.tasks if t.tool_name == "telegram_send_message").requires_approval
    assert isinstance(answer, DirectReply)


@pytest.mark.skipif(not os.getenv("LIVE_TELEGRAM"), reason="sends a real message: set LIVE_TELEGRAM=1")
async def test_telegram_sends_one_real_message(settings: Settings) -> None:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        pytest.skip("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    async with httpx.AsyncClient() as http:
        sent = await TelegramClient(http, settings.telegram_bot_token.get_secret_value()).send_message(
            settings.telegram_chat_id, "Personal AI Assistant: live integration test message."
        )
    assert sent.message_id > 0
