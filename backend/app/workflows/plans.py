"""What a planner returns. Both the mock and the LLM planner produce these two shapes."""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.workflows.models import PlanningInfo, WorkflowTask


@dataclass(frozen=True)
class Plan:
    reply: str
    goal: str
    tasks: list[WorkflowTask]
    # Mock-only failure injection, triggered by "simulate failure" in the message.
    fail_task_ids: frozenset[str] = field(default_factory=frozenset)
    planning: PlanningInfo | None = None


@dataclass(frozen=True)
class DirectReply:
    reply: str
    planning: PlanningInfo | None = None


class Planner(Protocol):
    async def plan(self, message: str, *, today: date) -> Plan | DirectReply:
        """Returns a validated plan or a direct reply. Never returns something unvalidated."""
        ...
