import asyncio
import itertools
from datetime import UTC, datetime

from app.tools import build_default_registry
from app.workflows.models import WorkflowRun
from app.workflows.planner import MockPlanner, Plan
from app.workflows.runner import WorkflowRunner

BRIEFING = "Give me a morning briefing and send it to Telegram"
# 1/100 of the demo latency: weather 9ms, calendar 13ms, gmail 17ms, summary 12ms, telegram 7ms.
FAST = 0.01


def make_runner(message: str = BRIEFING, scale: float = FAST, run_id: str = "run_1") -> WorkflowRunner:
    registry = build_default_registry(mock_latency_scale=scale)
    plan = MockPlanner(registry).build(message)
    assert isinstance(plan, Plan)
    run = WorkflowRun(
        id=run_id, conversation_id="conv_1", goal=plan.goal, tasks=plan.tasks, created_at=datetime.now(UTC)
    )
    counter = itertools.count(1)
    return WorkflowRunner(run, registry, fail_task_ids=plan.fail_task_ids, new_id=lambda p: f"{p}_{next(counter)}")


async def wait_for(predicate, timeout: float = 2.0) -> None:
    """Polls until predicate() is true; fails the test on timeout."""
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.002)


def statuses(runner: WorkflowRunner) -> dict[str, str]:
    return {t.id: t.status for t in runner.run.tasks}
