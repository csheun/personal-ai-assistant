"""Web search tool, in two implementations under the same name:

- `web_search_tool`: MOCKED canned results (MOCK_MODE=true).
- `make_web_search_tool(client)`: real results from Tavily.

Results are untrusted third-party content: they are only ever passed to the synthesizer as
fenced data, and snippets are trimmed so one page can't flood the prompt.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.providers.errors import ProviderError
from app.providers.tavily import TavilyClient
from app.tools.base import Tool, ToolInput
from app.tools.provider_errors import as_tool_failure


class WebSearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=300, description="The search query.")
    max_results: int = Field(default=3, ge=1, le=10, description="How many results to return (1-10).")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchOutput(BaseModel):
    query: str
    results: list[SearchResult]
    mocked: Literal[True] = True
    source: str = "mock"


async def _web_search(args: WebSearchInput) -> WebSearchOutput:
    results = [
        SearchResult(
            title=f"Mock result {i} for '{args.query}'",
            url=f"https://example.com/mock-search/{i}",
            snippet=f"This is placeholder search content about {args.query}. It is not real web data.",
        )
        for i in range(1, args.max_results + 1)
    ]
    return WebSearchOutput(query=args.query, results=results)


web_search_tool = Tool(
    name="web_search",
    description="Search the web for up-to-date information and return a list of results.",
    input_model=WebSearchInput,
    output_model=WebSearchOutput,
    handler=_web_search,
    mocked=True,
)


# --- real: Tavily ---------------------------------------------------------------------------

SNIPPET_CHARS = 600


class SearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=300, description="The search query.")
    max_results: int = Field(default=5, ge=1, le=10, description="How many results to return (1-10).")
    topic: Literal["general", "news"] = Field(default="general", description='"news" for current events and news.')
    time_range: Literal["day", "week", "month", "year"] | None = Field(
        default=None, description="Only results published within this period, e.g. 'week' for recent news."
    )


class WebResult(BaseModel):
    title: str
    url: str
    snippet: str
    published_date: str | None = None


class SearchOutput(BaseModel):
    query: str
    results: list[WebResult]
    source: str = "tavily"
    mocked: bool = False


def make_web_search_tool(client: TavilyClient, *, timeout_seconds: float | None = None) -> Tool[SearchInput, SearchOutput]:
    async def search(args: SearchInput) -> SearchOutput:
        try:
            hits = await client.search(args.query, max_results=args.max_results, topic=args.topic, time_range=args.time_range)
        except ProviderError as exc:
            raise as_tool_failure(exc) from exc
        # An empty list is a valid answer ("nothing found"), not a failure: the summary says so.
        results = [
            WebResult(title=_clean(h.title) or h.url, url=h.url, snippet=_clean(h.content)[:SNIPPET_CHARS], published_date=h.published_date)
            for h in hits
            if h.url.startswith(("https://", "http://"))
        ]
        return SearchOutput(query=args.query, results=results)

    return Tool(
        name="web_search",
        description=(
            "Search the web for up-to-date information. Returns titles, URLs, snippets and publish dates. "
            "For news or anything 'recent'/'latest', use topic 'news' with time_range 'week' (or 'day')."
        ),
        input_model=SearchInput,
        output_model=SearchOutput,
        handler=search,
        timeout_seconds=timeout_seconds,
    )


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
