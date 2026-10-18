"""MOCKED web search tool. Returns canned results; no external API is called.

Replace `_web_search` with a real provider (e.g. Tavily, Brave) in a later milestone.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInput


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
