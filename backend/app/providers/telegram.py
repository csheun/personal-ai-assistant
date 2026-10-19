"""Telegram Bot API client (https://core.telegram.org/bots/api#sendmessage).

The bot token is part of the request URL, so it must never be logged: main.py lowers the
httpx logger to WARNING, and errors here never include the URL or the raw exception text.

Delivery semantics: at most once. Errors are split by whether the message could have been sent:
- connection failed before the request was sent → definitely not sent ("unavailable")
- no response after sending (read timeout, dropped connection) → maybe sent ("uncertain")
- Telegram answered with an error → not sent (rate limit, bad chat, blocked bot...)
"""

import logging
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

from app.providers.errors import ProviderError

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096


class SentMessage(BaseModel):
    message_id: int
    sent_at: datetime


class TelegramClient:
    def __init__(self, http: httpx.AsyncClient, bot_token: str, *, timeout_seconds: float = 10.0) -> None:
        self._http = http
        self._token = bot_token
        self._timeout = timeout_seconds

    async def send_message(self, chat_id: str, text: str) -> SentMessage:
        url = f"{API_BASE}/bot{self._token}/sendMessage"
        body = {"chat_id": chat_id, "text": text[:MAX_MESSAGE_LENGTH], "link_preview_options": {"is_disabled": True}}
        try:
            response = await self._http.post(url, json=body, timeout=self._timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderError("telegram", "unavailable", "Couldn't reach Telegram, so the message was not sent.") from None
        except httpx.TransportError:
            # Sent (or partly sent) but no answer: Telegram may have delivered it.
            raise ProviderError(
                "telegram",
                "uncertain",
                "Telegram didn't confirm delivery in time. The message may or may not have been sent; "
                "check Telegram before trying again.",
            ) from None

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code == 200 and data.get("ok") and isinstance(data.get("result"), dict):
            result = data["result"]
            return SentMessage(
                message_id=int(result.get("message_id", 0)),
                sent_at=datetime.fromtimestamp(int(result.get("date", 0)), UTC),
            )

        description = str(data.get("description", ""))[:200]
        status = response.status_code
        logger.warning("Telegram rejected sendMessage: %s %s", status, description)
        if status == 429:
            retry_after = (data.get("parameters") or {}).get("retry_after")
            wait = f" Try again in {retry_after}s." if retry_after else ""
            raise ProviderError("telegram", "rate_limited", f"Telegram is rate limiting the bot; nothing was sent.{wait}")
        if status in (401, 404):
            raise ProviderError("telegram", "auth", "Telegram rejected the bot token; nothing was sent. Check TELEGRAM_BOT_TOKEN.")
        if status == 403:
            raise ProviderError(
                "telegram", "auth", "The bot isn't allowed to message this chat (start a chat with the bot first); nothing was sent."
            )
        if status == 400:
            raise ProviderError("telegram", "bad_request", f"Telegram rejected the message ({description or 'bad request'}); nothing was sent.")
        raise ProviderError("telegram", "unavailable", f"Telegram returned an error ({status}); nothing was sent.")
