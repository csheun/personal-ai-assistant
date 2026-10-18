"""MOCKED Telegram send. Simulates delivery; nothing is sent.

This tool has a side effect in the real world, so the workflow runner only executes it
after the user approves (see `requires_approval` in the planner).
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInput


class TelegramInput(ToolInput):
    chat: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=4096)


class TelegramOutput(BaseModel):
    chat: str
    characters: int
    delivered: Literal[False] = False
    note: str = "Mock mode: no message was sent to Telegram."
    mocked: Literal[True] = True


async def _send(args: TelegramInput) -> TelegramOutput:
    return TelegramOutput(chat=args.chat, characters=len(args.text))


telegram_tool = Tool(
    name="telegram_send_message",
    description="Send a Telegram message.",
    input_model=TelegramInput,
    output_model=TelegramOutput,
    handler=_send,
    mocked=True,
    side_effects=True,
)
