"""MOCKED AI summary. Builds a deterministic summary from upstream tool outputs; no LLM is called.

Milestone 4 replaces `_summarize` with an LLM call; the input/output contract stays the same.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInput


class SourceResult(BaseModel):
    tool_name: str
    output: dict[str, Any]


class SummarizeInput(ToolInput):
    sources: list[SourceResult] = Field(min_length=1, description="Outputs of the tasks this summary depends on.")


class SummarizeOutput(BaseModel):
    text: str
    mocked: Literal[True] = True


def _line(source: SourceResult) -> str | None:
    out = source.output
    match source.tool_name:
        case "get_weather":
            unit = "°C" if out.get("unit") == "celsius" else "°F"
            return f"{out['city']}: {out['temperature']:g}{unit}, {str(out['condition']).lower()}."
        case "calendar_list_events":
            first = out["events"][0]
            return f"{len(out['events'])} events today, starting with {first['title']} at {first['time']}."
        case "gmail_search":
            latest = out["messages"][-1]
            return f'{len(out["messages"])} new emails, including "{latest["subject"]}" from {latest["sender"]}.'
        case "web_search":
            return f"Found {len(out['results'])} recent articles about {out['query']}."
        case "document_search":
            return f'From your notes: "{out["passages"][0]["excerpt"]}"'
    return None


async def _summarize(args: SummarizeInput) -> SummarizeOutput:
    lines = [line for source in args.sources if (line := _line(source))]
    return SummarizeOutput(text=" ".join(lines) or "Nothing to summarize.")


summarize_tool = Tool(
    name="summarize",
    description="Summarize the results of earlier steps.",
    input_model=SummarizeInput,
    output_model=SummarizeOutput,
    handler=_summarize,
    mocked=True,
)
