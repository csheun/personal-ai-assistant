import json

import httpx
import pytest

from app.providers.tavily import SEARCH_URL, TavilyClient
from app.tools import ToolRegistry
from app.tools.web_search import SNIPPET_CHARS, make_web_search_tool
from tests.http_fakes import fake_http, raises

HITS = {
    "query": "AI news",
    "results": [
        {"title": "Model A ships", "url": "https://news.example/a", "content": "Big\n\n  news", "score": 0.9, "published_date": "Sun, 18 Oct 2026 08:00:00 GMT"},
        {"title": "", "url": "https://news.example/b", "content": "x" * 5000, "score": 0.5},
        {"title": "Bad scheme", "url": "javascript:alert(1)", "content": "nope"},
    ],
}  # fmt: skip


def search_registry(handler) -> tuple[ToolRegistry, list[httpx.Request]]:  # type: ignore[no-untyped-def]
    http, seen = fake_http(handler)
    registry = ToolRegistry()
    registry.register(make_web_search_tool(TavilyClient(http, "tvly-test-key")))
    return registry, seen


async def test_results_keep_urls_titles_and_dates() -> None:
    registry, seen = search_registry(lambda r: httpx.Response(200, json=HITS))
    result = await registry.execute("web_search", {"query": "AI news", "topic": "news", "time_range": "week"})

    assert result.ok, result.error
    results = result.output["results"]
    assert [r["url"] for r in results] == ["https://news.example/a", "https://news.example/b"]  # non-http dropped
    assert results[0] == {"title": "Model A ships", "url": "https://news.example/a", "snippet": "Big news",
                          "published_date": "Sun, 18 Oct 2026 08:00:00 GMT"}  # fmt: skip
    assert results[1]["title"] == "https://news.example/b" and len(results[1]["snippet"]) == SNIPPET_CHARS

    request = seen[0]
    assert str(request.url) == SEARCH_URL and request.headers["Authorization"] == "Bearer tvly-test-key"
    body = json.loads(request.content)
    expected = {"query": "AI news", "topic": "news", "time_range": "week", "max_results": 5, "include_answer": False}
    assert expected.items() <= body.items()


async def test_empty_results_are_a_valid_answer() -> None:
    registry, _ = search_registry(lambda r: httpx.Response(200, json={"query": "zzz", "results": []}))
    result = await registry.execute("web_search", {"query": "zzz"})
    assert result.ok and result.output["results"] == []


@pytest.mark.parametrize(
    ("handler", "code", "message"),
    [
        (raises(httpx.ConnectTimeout("slow")), "timeout", "didn't respond in time"),
        (lambda r: httpx.Response(401, json={"detail": {"error": "Unauthorized"}}), "provider_error", "rejected the server's API key"),
        (lambda r: httpx.Response(432), "provider_error", "usage limit"),
        (lambda r: httpx.Response(429), "provider_error", "usage limit"),
        (lambda r: httpx.Response(500), "provider_error", "error (500)"),
        (lambda r: httpx.Response(200, json={"results": [{"title": "no url"}]}), "provider_error", "unexpected data"),
    ],
)
async def test_provider_failures(handler, code: str, message: str) -> None:  # type: ignore[no-untyped-def]
    registry, _ = search_registry(handler)
    result = await registry.execute("web_search", {"query": "x"})
    assert not result.ok and result.error.code == code and message in result.error.message
    assert "tvly-test-key" not in result.error.message


async def test_arguments_are_validated_before_any_request() -> None:
    registry, seen = search_registry(lambda r: httpx.Response(200, json=HITS))
    result = await registry.execute("web_search", {"query": "x", "max_results": 50})
    assert result.error.code == "invalid_arguments" and seen == []
