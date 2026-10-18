from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.dependencies import Workflows
from app.workflows.models import ApprovalDecisionRequest, ApprovalRequest, WorkflowRun

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/{run_id}", response_model=WorkflowRun)
async def get_run(run_id: str, workflows: Workflows) -> WorkflowRun:
    """Current snapshot. `last_event_id` tells the client where to resume the event stream."""
    return workflows.get_run(run_id)


@router.post("/{run_id}/start", response_model=WorkflowRun)
async def start_run(run_id: str, workflows: Workflows) -> WorkflowRun:
    return workflows.start(run_id)


@router.post("/{run_id}/approve", response_model=ApprovalRequest)
async def resolve_approval(run_id: str, body: ApprovalDecisionRequest, workflows: Workflows) -> ApprovalRequest:
    """Approve or reject a pending approval request (`decision`: "approve" | "reject")."""
    return workflows.resolve_approval(run_id, body.approval_id, body.decision)


@router.post("/{run_id}/cancel", response_model=WorkflowRun)
async def cancel_run(run_id: str, workflows: Workflows) -> WorkflowRun:
    return workflows.cancel(run_id)


def _existing_run(run_id: str, workflows: Workflows) -> str:
    """Runs before streaming starts, so an unknown run is a normal 404 instead of a broken stream."""
    workflows.get_run(run_id)
    return run_id


def _resume_from(
    after: Annotated[int | None, Query(ge=0, description="Resume after this event id.")] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> int:
    """Where to resume. The browser's `Last-Event-ID` header wins: it only appears on an automatic
    reconnect and is always newer than the `?after=` the stream was first opened with."""
    if last_event_id and last_event_id.isdigit():
        return int(last_event_id)
    return after or 0


@router.get("/{run_id}/events", response_class=EventSourceResponse)
async def stream_events(
    request: Request,
    workflows: Workflows,
    run_id: Annotated[str, Depends(_existing_run)],
    after_id: Annotated[int, Depends(_resume_from)],
) -> AsyncIterator[ServerSentEvent]:
    """Server-Sent Events: replays events after `after_id`, then streams live ones, then closes.

    Each message's `data` is a WorkflowEvent envelope and its SSE `id` is the event id.
    Disconnecting only ends this stream; the run keeps going.
    """
    heartbeat = request.app.state.settings.sse_heartbeat_seconds
    yield ServerSentEvent(comment="stream open", retry=2000)
    async for event in workflows.follow(run_id, after_id, heartbeat_seconds=heartbeat):
        if event is None:
            yield ServerSentEvent(comment="keep-alive")
        else:
            yield ServerSentEvent(id=str(event.id), data=event.model_dump(mode="json"))
