"""MOCKED Telegram send. Simulates delivery; nothing is sent.

The input is only the text. The destination is fixed by server configuration, never by the
planner or the LLM, and the workflow runner only executes this tool after the user approves.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import ActionPreview, Tool, ToolInput

MOCK_DESTINATION = "Me (Saved Messages)"


class TelegramInput(ToolInput):
    text: str = Field(min_length=1, max_length=4096)


class TelegramOutput(BaseModel):
    chat: str
    characters: int
    delivered: bool = False
    note: str = "Mock mode: no message was sent to Telegram."
    mocked: Literal[True] = True


async def _send(args: TelegramInput) -> TelegramOutput:
    return TelegramOutput(chat=MOCK_DESTINATION, characters=len(args.text))


def _preview(args: TelegramInput) -> ActionPreview:
    return ActionPreview(
        action=f"Send a Telegram message to {MOCK_DESTINATION}",
        destination=f"Telegram · {MOCK_DESTINATION}",
        body=args.text,
    )


telegram_tool = Tool(
    name="telegram_send_message",
    description="Send the summary as a Telegram message to the user's configured chat.",
    input_model=TelegramInput,
    output_model=TelegramOutput,
    handler=_send,
    mocked=True,
    risk="external_write",
    bound_inputs=frozenset({"text"}),
    describe_action=_preview,
)
