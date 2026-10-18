"""Dependency-graph helpers. Python twin of `frontend/src/lib/workflow/graph.ts`."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.workflows.models import TERMINAL_TASK_STATUSES, WorkflowTask


class InvalidWorkflowError(ValueError):
    pass


def validate_dag(tasks: Sequence[WorkflowTask]) -> None:
    """Rejects duplicate ids, unknown dependencies and cycles."""
    ids = [t.id for t in tasks]
    if len(set(ids)) != len(ids):
        raise InvalidWorkflowError("Duplicate task ids")
    known = set(ids)
    for task in tasks:
        for dep in task.depends_on:
            if dep not in known:
                raise InvalidWorkflowError(f"Task {task.id} depends on unknown task {dep}")
    dependency_levels(tasks)


def dependency_levels(tasks: Sequence[WorkflowTask]) -> dict[str, int]:
    """Level 0 = no dependencies, otherwise 1 + the deepest dependency."""
    by_id = {t.id: t for t in tasks}
    levels: dict[str, int] = {}
    visiting: set[str] = set()

    def visit(task_id: str) -> int:
        if task_id in levels:
            return levels[task_id]
        if task_id in visiting:
            raise InvalidWorkflowError(f"Dependency cycle through task {task_id}")
        visiting.add(task_id)
        deps = by_id[task_id].depends_on
        level = 0 if not deps else 1 + max(visit(d) for d in deps)
        visiting.discard(task_id)
        levels[task_id] = level
        return level

    for task in tasks:
        visit(task.id)
    return levels


def is_terminal(task: WorkflowTask) -> bool:
    return task.status in TERMINAL_TASK_STATUSES


def ready_tasks(tasks: Sequence[WorkflowTask]) -> list[WorkflowTask]:
    """Pending tasks whose dependencies have all completed."""
    status = {t.id: t.status for t in tasks}
    return [t for t in tasks if t.status == "pending" and all(status[d] == "completed" for d in t.depends_on)]


@dataclass(frozen=True)
class Blocked:
    task: WorkflowTask
    blocker: WorkflowTask


def blocked_tasks(tasks: Sequence[WorkflowTask]) -> list[Blocked]:
    """Pending tasks that can never run because a dependency failed, was skipped or was cancelled."""
    by_id = {t.id: t for t in tasks}
    blocked = []
    for task in tasks:
        if task.status != "pending":
            continue
        blocker = next((by_id[d] for d in task.depends_on if by_id[d].status in {"failed", "skipped", "cancelled"}), None)
        if blocker:
            blocked.append(Blocked(task, blocker))
    return blocked


def parallel_saving_ms(tasks: Sequence[WorkflowTask]) -> int:
    """Total task time minus the critical path: what running in parallel saved (ignores approval waits)."""
    by_id = {t.id: t for t in tasks}
    finish: dict[str, int] = {}

    def finish_at(task: WorkflowTask) -> int:
        if task.id not in finish:
            start = max((finish_at(by_id[d]) for d in task.depends_on), default=0)
            finish[task.id] = start + (task.duration_ms or 0)
        return finish[task.id]

    critical_path = max((finish_at(t) for t in tasks), default=0)
    return sum(t.duration_ms or 0 for t in tasks) - critical_path
