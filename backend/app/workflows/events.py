"""Per-run event log with replay and live fan-out.

Producers append; any number of consumers iterate from an event id. A slow or
disconnected consumer never blocks the producer or other consumers.
"""

import asyncio
from collections.abc import AsyncIterator

from app.workflows.models import RUN_ENDING_EVENTS, WorkflowEvent


class EventLog:
    def __init__(self) -> None:
        self._events: list[WorkflowEvent] = []
        self._changed = asyncio.Condition()

    @property
    def events(self) -> list[WorkflowEvent]:
        return list(self._events)

    @property
    def next_id(self) -> int:
        return len(self._events) + 1

    @property
    def closed(self) -> bool:
        return bool(self._events) and self._events[-1].type in RUN_ENDING_EVENTS

    def append(self, event: WorkflowEvent) -> None:
        if event.id != self.next_id:
            raise ValueError(f"Event id {event.id} out of order (expected {self.next_id})")
        self._events.append(event)
        # Wake readers without awaiting: appends happen synchronously inside the runner.
        asyncio.get_running_loop().create_task(self._notify())

    async def _notify(self) -> None:
        async with self._changed:
            self._changed.notify_all()

    async def follow(self, after_id: int = 0, heartbeat_seconds: float | None = None) -> AsyncIterator[WorkflowEvent | None]:
        """Yields events with id > after_id, then live ones, until the run ends.

        Yields None every `heartbeat_seconds` of silence so the caller can send keep-alives.
        """
        position = after_id
        while True:
            while position < len(self._events):
                event = self._events[position]
                position += 1
                yield event
                if event.type in RUN_ENDING_EVENTS:
                    return
            if self.closed:
                return
            async with self._changed:
                if position < len(self._events):
                    continue
                try:
                    await asyncio.wait_for(self._changed.wait(), timeout=heartbeat_seconds)
                except TimeoutError:
                    yield None
