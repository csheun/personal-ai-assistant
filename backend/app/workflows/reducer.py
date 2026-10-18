"""Applies one event to a run snapshot. Python twin of `frontend/src/lib/workflow/reducer.ts`.

The runner never mutates a run directly: it creates an event and calls `apply_event`.
That guarantees that a client replaying the SSE stream reaches exactly the snapshot
`GET /api/workflows/{id}` returns. `tests/test_contract.py` checks both sides agree.
"""

from app.workflows.models import (
    ApprovalRequested,
    ApprovalResolved,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunStarted,
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskSkipped,
    TaskStarted,
    WorkflowEvent,
    WorkflowRun,
    WorkflowTask,
)


def apply_event(run: WorkflowRun, event: WorkflowEvent) -> WorkflowRun:
    updated = _reduce(run, event)
    return updated.model_copy(update={"last_event_id": event.id})


def _reduce(run: WorkflowRun, event: WorkflowEvent) -> WorkflowRun:
    def update_task(task_id: str | None, **patch: object) -> list[WorkflowTask]:
        return [t.model_copy(update=patch) if t.id == task_id else t for t in run.tasks]

    match event:
        case RunStarted():
            return run.model_copy(update={"status": "running", "started_at": event.timestamp})

        case TaskStarted():
            waiting = any(a.status == "pending" and a.task_id != event.task_id for a in run.approvals)
            return run.model_copy(
                update={
                    "status": "waiting_for_approval" if waiting else "running",
                    "tasks": update_task(event.task_id, status="running", started_at=event.timestamp),
                }
            )

        case TaskCompleted():
            return run.model_copy(
                update={
                    "tasks": update_task(
                        event.task_id,
                        status="completed",
                        finished_at=event.timestamp,
                        duration_ms=event.data.duration_ms,
                        result=event.data.result,
                    )
                }
            )

        case TaskFailed():
            return run.model_copy(
                update={
                    "tasks": update_task(
                        event.task_id,
                        status="failed",
                        finished_at=event.timestamp,
                        duration_ms=event.data.duration_ms,
                        result=event.data.result,
                        status_reason=event.data.reason,
                    )
                }
            )

        case TaskSkipped():
            return run.model_copy(
                update={"tasks": update_task(event.task_id, status="skipped", status_reason=event.data.reason)}
            )

        case TaskCancelled():
            task = next((t for t in run.tasks if t.id == event.task_id), None)
            started = task.started_at if task else None
            ran_for = round((event.timestamp - started).total_seconds() * 1000) if started else None
            return run.model_copy(
                update={
                    "tasks": update_task(
                        event.task_id,
                        status="cancelled",
                        finished_at=event.timestamp if started else None,
                        duration_ms=ran_for,
                        status_reason="Stopped because you cancelled the run.",
                    )
                }
            )

        case ApprovalRequested():
            return run.model_copy(
                update={
                    "status": "waiting_for_approval",
                    "tasks": update_task(event.task_id, status="waiting_for_approval"),
                    "approvals": [*run.approvals, event.data.approval],
                }
            )

        case ApprovalResolved():
            approvals = [event.data.approval if a.id == event.data.approval.id else a for a in run.approvals]
            still_waiting = any(a.status == "pending" for a in approvals)
            status = run.status if still_waiting or run.status != "waiting_for_approval" else "running"
            return run.model_copy(update={"approvals": approvals, "status": status})

        case RunCompleted():
            return run.model_copy(
                update={"status": "completed", "summary": event.data.summary, "finished_at": event.timestamp}
            )

        case RunFailed():
            return run.model_copy(update={"status": "failed", "finished_at": event.timestamp})

        case RunCancelled():
            return run.model_copy(update={"status": "cancelled", "finished_at": event.timestamp})

    raise ValueError(f"Unknown event type: {event.type}")  # pragma: no cover
