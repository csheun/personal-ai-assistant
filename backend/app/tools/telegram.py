"""Telegram send tool, in two implementations under the same name:

- `telegram_tool`: SIMULATED (MOCK_MODE=true, or live mode without Telegram configured).
- `make_telegram_tool(client, chat_id, label)`: really sends via the Bot API.

Both take only the text. The destination is fixed by server configuration, never by the
planner or the LLM. The workflow runner only executes this tool after the user approves the
exact text (risk="external_write").
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.providers.errors import ProviderError
from app.providers.telegram import TelegramClient
from app.tools.base import ActionPreview, Tool, ToolFailure, ToolInput
from app.tools.provider_errors import as_tool_failure

MOCK_DESTINATION = "Me (Saved Messages)"


class TelegramInput(ToolInput):
    text: str = Field(min_length=1, max_length=4096)


class TelegramOutput(BaseModel):
    chat: str
    characters: int
    delivered: bool
    message_id: int | None = None
    sent_at: datetime | None = None
    note: str | None = None
    mocked: bool


def _preview(label: str):  # type: ignore[no-untyped-def]
    def describe(args: TelegramInput) -> ActionPreview:
        return ActionPreview(action=f"Send a Telegram message to {label}", destination=f"Telegram · {label}", body=args.text)

    return describe


# --- simulated ------------------------------------------------------------------------------


async def _simulate(args: TelegramInput) -> TelegramOutput:
    return TelegramOutput(
        chat=MOCK_DESTINATION,
        characters=len(args.text),
        delivered=False,
        note="Simulated: no message was sent to Telegram.",
        mocked=True,
    )


telegram_tool = Tool(
    name="telegram_send_message",
    description="Send the summary as a Telegram message to the user's configured chat.",
    input_model=TelegramInput,
    output_model=TelegramOutput,
    handler=_simulate,
    mocked=True,
    risk="external_write",
    bound_inputs=frozenset({"text"}),
    describe_action=_preview(MOCK_DESTINATION),
)


# --- real -----------------------------------------------------------------------------------


def make_telegram_tool(
    client: TelegramClient, *, chat_id: str, label: str, timeout_seconds: float | None = None
) -> Tool[TelegramInput, TelegramOutput]:
    async def send(args: TelegramInput) -> TelegramOutput:
        try:
            sent = await client.send_message(chat_id, args.text)
        except ProviderError as exc:
            if exc.kind == "uncertain":
                raise ToolFailure("delivery_unknown", exc.message) from None
            raise as_tool_failure(exc) from None
        return TelegramOutput(
            chat=label,
            characters=len(args.text),
            delivered=True,
            message_id=sent.message_id,
            sent_at=sent.sent_at,
            mocked=False,
        )

    return Tool(
        name="telegram_send_message",
        description="Send the summary as a Telegram message to the user's configured chat.",
        input_model=TelegramInput,
        output_model=TelegramOutput,
        handler=send,
        risk="external_write",
        bound_inputs=frozenset({"text"}),
        describe_action=_preview(label),
        timeout_seconds=timeout_seconds,
    )
