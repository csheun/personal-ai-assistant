"""MOCKED Gmail search tool. Returns fixed messages; no API is called."""

from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInput


class GmailInput(ToolInput):
    query: str = Field(min_length=1, max_length=200, description="Gmail search query, e.g. 'is:unread'.")


class EmailSummary(BaseModel):
    sender: str
    subject: str
    received: str


class GmailOutput(BaseModel):
    query: str
    messages: list[EmailSummary]
    mocked: Literal[True] = True


async def _search(args: GmailInput) -> GmailOutput:
    messages = [
        EmailSummary(sender="DBS Bank", subject="Your statement is ready", received="07:12"),
        EmailSummary(sender="Priya", subject="Lunch — still on?", received="08:03"),
    ]
    return GmailOutput(query=args.query, messages=messages)


gmail_tool = Tool(
    name="gmail_search",
    description="Search the user's email.",
    input_model=GmailInput,
    output_model=GmailOutput,
    handler=_search,
    mocked=True,
)
