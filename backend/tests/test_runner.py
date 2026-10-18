import asyncio

import pytest

from app.workflows.reducer import apply_event
from app.workflows.errors import NotFound, WorkflowConflict
from tests.workflow_helpers import make_runner, statuses, wait_for


async def test_independent_tasks_run_concurrently_and_dependants_wait() -> None:
    runner = make_runner()
    runner.start()
    # Right after start, all three independent tasks are running and nothing else is.
    assert statuses(runner) == {"t1": "running", "t2": "running", "t3": "running", "t4": "pending", "t5": "pending"}

    await wait_for(lambda: runner.run.status == "waiting_for_approval")
    t1, t2, t3, t4, _ = runner.run.tasks
    starts = [t.started_at for t in (t1, t2, t3)]
    assert (max(starts) - min(starts)).total_seconds() < 0.005  # same tick, give or take clock jitter
    assert t4.started_at >= max(t1.finished_at, t2.finished_at, t3.finished_at)
    # Wall time for step 1 is the slowest task (~17ms), not the sum (~39ms).
    step1_wall = (max(t1.finished_at, t2.finished_at, t3.finished_at) - t1.started_at).total_seconds() * 1000
    assert step1_wall < t1.duration_ms + t2.duration_ms + t3.duration_ms


async def test_approval_runs_the_side_effect_with_the_summary_text() -> None:
    runner = make_runner()
    runner.start()
    await wait_for(lambda: runner.run.status == "waiting_for_approval")

    approval = runner.run.approvals[0]
    summary_text = runner.run.tasks[3].result.output["text"]
    assert approval.preview.body == summary_text
    assert statuses(runner)["t5"] == "waiting_for_approval"

    runner.resolve_approval(approval.id, "approve")
    run = await asyncio.wait_for(runner.wait_until_finished(), 2)

    assert run.status == "completed"
    telegram = run.tasks[4]
    assert telegram.result.arguments["text"] == summary_text
    assert telegram.result.output["delivered"] is False
    assert "nothing was actually sent" in run.summary


async def test_rejection_skips_the_side_effect() -> None:
    runner = make_runner()
    runner.start()
    await wait_for(lambda: runner.run.status == "waiting_for_approval")
    runner.resolve_approval(runner.run.approvals[0].id, "reject")
    run = await asyncio.wait_for(runner.wait_until_finished(), 2)

    assert run.status == "completed"
    assert run.tasks[4].status == "skipped"
    assert run.tasks[4].started_at is None
    assert "rejected" in run.summary
    with pytest.raises(WorkflowConflict, match="already rejected"):
        runner.resolve_approval(run.approvals[0].id, "approve")
    with pytest.raises(NotFound):
        runner.resolve_approval("nope", "approve")


async def test_cancel_stops_running_tasks_and_nothing_completes_later() -> None:
    runner = make_runner(scale=1.0)  # real latency, so tasks are mid-flight
    runner.start()
    await asyncio.sleep(0.05)
    runner.cancel()

    assert runner.run.status == "cancelled"
    assert set(statuses(runner).values()) == {"cancelled"}
    events_at_cancel = len(runner.log.events)
    await asyncio.sleep(0.05)
    assert len(runner.log.events) == events_at_cancel
    with pytest.raises(WorkflowConflict):
        runner.cancel()


async def test_cancel_expires_pending_approval() -> None:
    runner = make_runner()
    runner.start()
    await wait_for(lambda: runner.run.status == "waiting_for_approval")
    runner.cancel()
    assert runner.run.approvals[0].status == "expired"
    assert statuses(runner)["t5"] == "cancelled"


async def test_failure_skips_dependants_and_fails_the_run() -> None:
    runner = make_runner("Check the weather in Oslo and simulate failure")
    runner.start()
    run = await asyncio.wait_for(runner.wait_until_finished(), 2)

    assert run.status == "failed"
    assert statuses(runner) == {"t1": "failed", "t2": "skipped"}
    assert run.tasks[0].result.error.code == "simulated_failure"
    assert "Check Oslo weather" in run.tasks[1].status_reason


async def test_cannot_start_twice() -> None:
    runner = make_runner()
    runner.start()
    with pytest.raises(WorkflowConflict):
        runner.start()
    runner.cancel()


async def test_events_replay_to_the_same_snapshot() -> None:
    runner = make_runner()
    initial = runner.run
    runner.start()
    await wait_for(lambda: runner.run.status == "waiting_for_approval")
    runner.resolve_approval(runner.run.approvals[0].id, "approve")
    final = await asyncio.wait_for(runner.wait_until_finished(), 2)

    events = runner.log.events
    assert [e.id for e in events] == list(range(1, len(events) + 1))
    replayed = initial
    for event in events:
        replayed = apply_event(replayed, event)
    assert replayed == final
    assert final.last_event_id == len(events)


async def test_a_task_is_never_started_twice() -> None:
    runner = make_runner()
    runner.start()
    await wait_for(lambda: runner.run.status == "waiting_for_approval")
    runner._spawn(runner._task("t1"))  # a buggy second start of a finished task
    started = [e for e in runner.log.events if e.type == "task.started" and e.task_id == "t1"]
    assert len(started) == 1
    runner.cancel()
