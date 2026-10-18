import json
import logging
from datetime import datetime

import httpx
import pytest

from app.providers.errors import ProviderError
from app.providers.telegram import TelegramClient
from app.tools import ToolRegistry
from app.tools.telegram import make_telegram_tool
from tests.http_fakes import fake_http, raises

TOKEN = "123456:SECRET-bot-token"
OK = {"ok": True, "result": {"message_id": 42, "date": 1792400000, "chat": {"id": 99}}}


def telegram(handler) -> tuple[ToolRegistry, list[httpx.Request]]:  # type: ignore[no-untyped-def]
    http, seen = fake_http(handler)
    registry = ToolRegistry()
    registry.register(make_telegram_tool(TelegramClient(http, TOKEN), chat_id="99", label="Saved Messages"))
    return registry, seen


async def test_sends_to_the_configured_chat_and_records_delivery() -> None:
    registry, seen = telegram(lambda r: httpx.Response(200, json=OK))
    result = await registry.execute("telegram_send_message", {"text": "Storms tomorrow."})

    assert result.ok
    out = result.output
    assert (out["chat"], out["delivered"], out["message_id"], out["mocked"]) == ("Saved Messages", True, 42, False)
    assert datetime.fromisoformat(out["sent_at"]).timestamp() == 1792400000
    assert len(seen) == 1
    assert seen[0].url.path == f"/bot{TOKEN}/sendMessage"
    body = json.loads(seen[0].content)
    assert body["chat_id"] == "99" and body["text"] == "Storms tomorrow."


def test_the_llm_cannot_choose_the_chat() -> None:
    registry, _ = telegram(lambda r: httpx.Response(200, json=OK))
    tool = registry.get("telegram_send_message")
    assert set(tool.input_model.model_fields) == {"text"}
    assert tool.risk == "external_write" and tool.bound_inputs == frozenset({"text"})


@pytest.mark.parametrize(
    ("handler", "code", "message"),
    [
        (raises(httpx.ConnectError("refused")), "provider_error", "was not sent"),
        (raises(httpx.ReadTimeout("no answer")), "delivery_unknown", "may or may not have been sent"),
        (raises(httpx.RemoteProtocolError("dropped")), "delivery_unknown", "may or may not have been sent"),
        (lambda r: httpx.Response(429, json={"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 7}}), "provider_error", "Try again in 7s"),
        (lambda r: httpx.Response(401, json={"ok": False, "description": "Unauthorized"}), "provider_error", "TELEGRAM_BOT_TOKEN"),
        (lambda r: httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"}), "provider_error", "isn't allowed"),
        (lambda r: httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"}), "provider_error", "chat not found"),
        (lambda r: httpx.Response(502, text="gateway"), "provider_error", "nothing was sent"),
    ],
)
async def test_failures_say_whether_the_message_could_have_been_sent(handler, code: str, message: str) -> None:  # type: ignore[no-untyped-def]
    registry, seen = telegram(handler)
    result = await registry.execute("telegram_send_message", {"text": "hi"})
    assert not result.ok and result.error.code == code and message in result.error.message
    assert TOKEN not in result.error.message and "SECRET" not in result.error.message
    assert len(seen) == 1  # never retried


async def test_registry_timeout_on_a_send_is_delivery_unknown_not_not_sent() -> None:
    import asyncio

    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json=OK)

    http = httpx.AsyncClient(transport=httpx.MockTransport(hang))
    registry = ToolRegistry()
    registry.register(make_telegram_tool(TelegramClient(http, TOKEN), chat_id="99", label="x", timeout_seconds=0.05))
    result = await registry.execute("telegram_send_message", {"text": "hi"})
    assert result.error.code == "delivery_unknown"


async def test_client_reports_uncertain_separately() -> None:
    http, _ = fake_http(raises(httpx.ReadTimeout("x")))
    with pytest.raises(ProviderError) as caught:
        await TelegramClient(http, TOKEN).send_message("99", "hi")
    assert caught.value.kind == "uncertain"


def test_bot_token_is_not_logged_by_httpx() -> None:
    from app.config import Settings
    from app.main import create_app

    create_app(Settings(_env_file=None))  # type: ignore[call-arg]
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
