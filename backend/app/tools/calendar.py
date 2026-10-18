"""MOCKED Google Calendar tool. Returns fixed events; no API is called."""

from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInput


class CalendarInput(ToolInput):
    date: str = Field(default="today", max_length=20, description='"today" or an ISO date (YYYY-MM-DD).')


class CalendarEvent(BaseModel):
    time: str
    title: str


class CalendarOutput(BaseModel):
    date: str
    events: list[CalendarEvent]
    mocked: Literal[True] = True


async def _list_events(args: CalendarInput) -> CalendarOutput:
    events = [
        CalendarEvent(time="09:30", title="Team standup"),
        CalendarEvent(time="13:00", title="Lunch with Priya"),
        CalendarEvent(time="16:00", title="Design review"),
    ]
    return CalendarOutput(date=args.date, events=events)


calendar_tool = Tool(
    name="calendar_list_events",
    description="List calendar events for a day.",
    input_model=CalendarInput,
    output_model=CalendarOutput,
    handler=_list_events,
    mocked=True,
)
