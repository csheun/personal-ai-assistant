"""Tavily search client (https://docs.tavily.com/documentation/api-reference/endpoint/search).

Requires WEB_SEARCH_API_KEY. Everything returned is untrusted third-party content.
"""

import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from app.providers.errors import ProviderError

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.tavily.com/search"


class SearchHit(BaseModel):
    title: str = ""
    url: str
    content: str = ""
    score: float | None = None
    published_date: str | None = None


class TavilyClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str, *, timeout_seconds: float = 10.0) -> None:
        self._http = http
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        topic: Literal["general", "news"] = "general",
        time_range: Literal["day", "week", "month", "year"] | None = None,
    ) -> list[SearchHit]:
        body: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "topic": topic,
            "search_depth": "basic",
            "include_answer": False,  # we want sources, not the provider's own summary
            "include_raw_content": False,
        }
        if time_range:
            body["time_range"] = time_range
        try:
            response = await self._http.post(
                SEARCH_URL, json=body, headers={"Authorization": f"Bearer {self._api_key}"}, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("tavily", "timeout", "The search service didn't respond in time.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("tavily", "unavailable", "Couldn't reach the search service.") from exc

        status = response.status_code
        if status in (401, 403):
            raise ProviderError("tavily", "auth", "The search service rejected the server's API key.")
        if status == 429 or status == 432 or status == 433:  # 432/433: plan or pay-as-you-go limit reached
            raise ProviderError("tavily", "rate_limited", "The search service's usage limit was reached. Try again later.")
        if status == 400:
            logger.warning("Tavily rejected request: %s", response.text[:300])
            raise ProviderError("tavily", "bad_request", "The search service rejected the query.")
        if status >= 400:
            raise ProviderError("tavily", "unavailable", f"The search service returned an error ({status}).")

        try:
            data = response.json()
            return [SearchHit.model_validate(item) for item in data.get("results") or []]
        except (ValueError, AttributeError, ValidationError) as exc:
            raise ProviderError("tavily", "bad_response", "The search service returned unexpected data.") from exc
