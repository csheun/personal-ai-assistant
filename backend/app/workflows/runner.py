"""Executes one workflow run with asyncio. Independent of HTTP: nothing here knows about requests.

Rules (identical to the frontend's mock engine):
- A task starts when all its dependencies have completed, so independent tasks run concurrently.
- If a dependency fails, is skipped or is cancelled, dependants are skipped.
- `requires_approval` tasks wait in `waiting_for_approval`; approve runs them, reject skips them.
- Cancel stops running tasks, expires open approvals and cancels everything unfinished.

Every state change is an event: `_emit` builds it, applies it with `apply_event`, and appends
it to the run's EventLog. All mutations happen on the event loop between awaits, so no locks
are needed.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.tools import ToolError, ToolRegistry, ToolResult
from app.tools.base import ActionPreview
from app.workflows.bindings import resolve_arguments
from app.workflows.errors import NotFound, WorkflowConflict
from app.workflows.events import EventLog
from app.workflows.graph import blocked_tasks, is_terminal, ready_tasks, validate_dag
from app.workflows.models import (
    TERMINAL_RUN_STATUSES,
    ApprovalData,
    ApprovalDecision,
    ApprovalPreview,
    ApprovalRequest,
    ApprovalRequested,
    ApprovalResolved,
    ReasonData,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunStarted,
    SummaryData,
    TaskCancelled,
    TaskCompleted,
    TaskCompletedData,
    TaskFailed,
    TaskFailedData,
    TaskSkipped,
    TaskStarted,
    WorkflowRun,
    WorkflowTask,
)
from app.workflows.reducer import apply_event

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkflowRunner:
    def __init__(
        self,
        run: WorkflowRun,
        tools: ToolRegistry,
        *,
        fail_task_ids: frozenset[str] = frozenset(),
        clock: Clock = utc_now,
        new_id: Callable[[str], str],
    ) -> None:
        validate_dag(run.tasks)
        self._run = run
        self._tools = tools
        self._fail = fail_task_ids
        self._clock = clock
        self._new_id = new_id
        self.log = EventLog()
        self._jobs: dict[str, asyncio.Task[None]] = {}
        self._done = asyncio.Event()

    @property
    def run(self) -> WorkflowRun:
        return self._run

    async def wait_until_finished(self) -> WorkflowRun:
        await self._done.wait()
        return self._run

    # --- commands ----------------------------------------------------------------

    def start(self) -> None:
        if self._run.status != "planned":
            raise WorkflowConflict("This run has already started.")
        self._emit(RunStarted)
        self._advance()

    def cancel(self) -> None:
        if self._run.status in TERMINAL_RUN_STATUSES:
            raise WorkflowConflict("This run has already finished.")
        for job in self._jobs.values():
            job.cancel()
        self._jobs.clear()
        for approval in [a for a in self._run.approvals if a.status == "pending"]:
            expired = approval.model_copy(update={"status": "expired", "resolved_at": self._clock()})
            self._emit(ApprovalResolved, task_id=approval.task_id, data=ApprovalData(approval=expired))
        for task in [t for t in self._run.tasks if not is_terminal(t)]:
            self._emit(TaskCancelled, task_id=task.id)
        self._emit(RunCancelled)

    def resolve_approval(self, approval_id: str, decision: ApprovalDecision) -> ApprovalRequest:
        approval = next((a for a in self._run.approvals if a.id == approval_id), None)
        if approval is None:
            raise NotFound("Approval request not found.")
        if approval.status != "pending":
            raise WorkflowConflict(f"This request was already {approval.status}.")

        resolved = approval.model_copy(
            update={"status": "approved" if decision == "approve" else "rejected", "resolved_at": self._clock()}
        )
        self._emit(ApprovalResolved, task_id=approval.task_id, data=ApprovalData(approval=resolved))
        if decision == "approve":
            self._spawn(self._task(approval.task_id))
        else:
            self._emit(
                TaskSkipped,
                task_id=approval.task_id,
                data=ReasonData(reason="You rejected this action, so nothing was sent."),
            )
            self._advance()
        return resolved

    # --- scheduling ------------------------------------------------------------------

    def _advance(self) -> None:
        if self._run.status in TERMINAL_RUN_STATUSES:
            return
        # Skipping can block further dependants, so repeat until stable.
        while blocked := blocked_tasks(self._run.tasks):
            for item in blocked:
                reason = f'Skipped because "{item.blocker.title}" didn\'t complete.'
                self._emit(TaskSkipped, task_id=item.task.id, data=ReasonData(reason=reason))

        for task in ready_tasks(self._run.tasks):
            if task.requires_approval:
                self._request_approval(task)
            else:
                self._spawn(task)

        if all(is_terminal(t) for t in self._run.tasks):
            self._finish()

    def _spawn(self, task: WorkflowTask) -> None:
        self._emit(TaskStarted, task_id=task.id)
        self._jobs[task.id] = asyncio.create_task(self._execute(task.id), name=f"{self._run.id}:{task.id}")

    def _request_approval(self, task: WorkflowTask) -> None:
        # The tool describes its own action from validated input, so the card shows exactly what will run.
        tool = self._tools.get(task.tool_name)
        arguments = resolve_arguments(task, self._upstream(task))
        if tool is None or tool.describe_action is None:
            preview = ActionPreview(action=f"Run {task.title}", destination=task.tool_name, body=str(arguments))
        else:
            preview = tool.describe_action(tool.input_model.model_validate(arguments))
        approval = ApprovalRequest(
            id=self._new_id("apr"),
            run_id=self._run.id,
            task_id=task.id,
            tool_name=task.tool_name,
            action=preview.action,
            preview=ApprovalPreview(destination=preview.destination, body=preview.body),
            status="pending",
            created_at=self._clock(),
        )
        self._emit(ApprovalRequested, task_id=task.id, data=ApprovalData(approval=approval))

    async def _execute(self, task_id: str) -> None:
        task = self._task(task_id)
        started = self._clock()
        try:
            result = await self._tools.execute(task.tool_name, resolve_arguments(task, self._upstream(task)))
        except asyncio.CancelledError:
            return  # cancel() already emitted the events
        except Exception:  # the registry contains tool errors; this is a bug guard
            logger.exception("Unexpected error running %s", task_id)
            result = ToolResult(
                tool_name=task.tool_name,
                arguments=task.arguments,
                ok=False,
                error=ToolError(code="execution_failed", message="The tool failed while running."),
            )
        finally:
            self._jobs.pop(task_id, None)

        if task_id in self._fail:
            result = _simulated_failure(result)
        duration = round((self._clock() - started).total_seconds() * 1000)

        if result.ok:
            self._emit(TaskCompleted, task_id=task_id, data=TaskCompletedData(result=result, duration_ms=duration))
        else:
            reason = result.error.message if result.error else "The tool failed."
            self._emit(
                TaskFailed, task_id=task_id, data=TaskFailedData(result=result, duration_ms=duration, reason=reason)
            )
        self._advance()

    def _finish(self) -> None:
        failed = [t for t in self._run.tasks if t.status == "failed"]
        if failed:
            names = ", ".join(f'"{t.title}"' for t in failed)
            self._emit(RunFailed, data=ReasonData(reason=f"{names} failed, so the run couldn't finish."))
        else:
            self._emit(RunCompleted, data=SummaryData(summary=_final_summary(self._run)))

    # --- helpers ----------------------------------------------------------------------

    def _task(self, task_id: str) -> WorkflowTask:
        return next(t for t in self._run.tasks if t.id == task_id)

    def _upstream(self, task: WorkflowTask) -> list[WorkflowTask]:
        return [self._task(d) for d in task.depends_on]

    def _emit(self, event_type: type, *, task_id: str | None = None, data: Any = None) -> None:
        fields: dict[str, Any] = {"id": self.log.next_id, "run_id": self._run.id, "timestamp": self._clock()}
        if task_id is not None:
            fields["task_id"] = task_id
        if data is not None:
            fields["data"] = data
        event = event_type(**fields)
        self._run = apply_event(self._run, event)
        self.log.append(event)
        if self._run.status in TERMINAL_RUN_STATUSES:
            self._done.set()


_FAILURE_MESSAGES = {
    "get_weather": "The weather service didn't respond in time.",
    "calendar_list_events": "Google Calendar returned an authorization error.",
    "gmail_search": "Gmail rate-limited the request.",
    "web_search": "The search provider returned an error.",
    "document_search": "The document index is unavailable.",
    "summarize": "The language model request failed.",
    "telegram_send_message": "Telegram rejected the message.",
}


def _simulated_failure(result: ToolResult) -> ToolResult:
    message = _FAILURE_MESSAGES.get(result.tool_name, "The tool failed.")
    return result.model_copy(
        update={"ok": False, "output": None, "error": ToolError(code="simulated_failure", message=message)}
    )


def _final_summary(run: WorkflowRun) -> str:
    summary_task = next((t for t in run.tasks if t.tool_name == "summarize"), None)
    output = summary_task.result.output if summary_task and summary_task.result else None
    text = str((output or {}).get("text", "All steps finished."))
    telegram = next((t for t in run.tasks if t.tool_name == "telegram_send_message"), None)
    if telegram is None:
        return text
    if telegram.status == "completed":
        return f"{text}\n\nYou approved the Telegram message. In mock mode nothing was actually sent."
    return f"{text}\n\nI didn't send anything to Telegram because you rejected the message."
