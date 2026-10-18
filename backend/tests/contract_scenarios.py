"""Records deterministic workflow scenarios from the real Python runner.

Output: `contracts/workflow-scenarios.json` (repo root), shared with the frontend:
- backend `tests/test_contract.py` checks the runner still produces exactly this file;
- frontend `tests/unit/contract.test.ts` replays each event list through the TypeScript
  reducer and must reach the same final snapshot.

Regenerate after an intentional contract change:  python -m tests.contract_scenarios --write
"""

import asyncio
import itertools
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.tools import build_default_registry
from app.workflows.models import WorkflowRun
from app.workflows.planner import MockPlanner, Plan
from app.workflows.runner import WorkflowRunner

FIXTURE = Path(__file__).resolve().parents[2] / "contracts" / "workflow-scenarios.json"
BRIEFING = "Give me a morning briefing and send it to Telegram"


class StepClock:
    """Each reading is 100ms after the previous one: deterministic timestamps and durations."""

    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self._now += timedelta(milliseconds=100)
        return self._now


async def _record(name: str, message: str, action: str) -> dict[str, Any]:
    tools = build_default_registry(mock_latency_scale=0)  # instant tools: order is deterministic
    plan = MockPlanner(tools).plan(message)
    assert isinstance(plan, Plan)
    clock, ids = StepClock(), itertools.count(1)
    run = WorkflowRun(id=f"run_{name}", conversation_id="conv_1", goal=plan.goal, tasks=plan.tasks, created_at=clock())
    # Tool outputs that embed wall-clock time are pinned so the fixture is stable.
    runner = WorkflowRunner(run, tools, fail_task_ids=plan.fail_task_ids, clock=clock, new_id=lambda p: f"{p}_{next(ids)}")
    initial = runner.run

    runner.start()
    if action == "cancel":
        runner.cancel()  # tasks are mid-flight: nothing has had a chance to finish
    else:
        while runner.run.status not in {"waiting_for_approval", "completed", "failed"}:
            await asyncio.sleep(0)
        if action in {"approve", "reject"}:
            runner.resolve_approval(runner.run.approvals[0].id, action)
    await asyncio.wait_for(runner.wait_until_finished(), 2)

    return {
        "name": name,
        "initial": _stable(initial.model_dump(mode="json")),
        "events": [_stable(e.model_dump(mode="json")) for e in runner.log.events],
        "final": _stable(runner.run.model_dump(mode="json")),
    }


def _stable(value: Any) -> Any:
    """Replaces the weather tool's wall-clock `observed_at` with a constant."""
    if isinstance(value, dict):
        return {k: ("2026-01-01T08:00:00Z" if k == "observed_at" else _stable(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_stable(v) for v in value]
    return value


async def record_all() -> dict[str, Any]:
    return {
        "scenarios": [
            await _record("approve", BRIEFING, "approve"),
            await _record("reject", BRIEFING, "reject"),
            await _record("cancel", BRIEFING, "cancel"),
            await _record("failure", "Check the weather in Oslo and simulate failure", "none"),
        ]
    }


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    if "--write" in sys.argv:
        FIXTURE.write_text(render(asyncio.run(record_all())))
        print(f"wrote {FIXTURE}")
