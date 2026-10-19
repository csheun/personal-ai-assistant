import asyncio

from app.tools import build_default_registry
from app.workflows.models import SendMessageRequest
from app.workflows.planner import MockPlanner
from app.workflows.service import WorkflowService
from tests.workflow_helpers import BRIEFING, wait_for


def make_service(scale: float = 0.01) -> WorkflowService:
    tools = build_default_registry(mock_latency_scale=scale)
    return WorkflowService(tools, MockPlanner(tools))


async def new_run(service: WorkflowService) -> str:
    return (await service.send_message(SendMessageRequest(message=BRIEFING))).run.id


async def test_live_stream_delivers_transitions_in_order() -> None:
    service = make_service()
    run_id = await new_run(service)
    received = []

    async def consume() -> None:
        async for event in service.follow(run_id):
            received.append(event)

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)  # subscribed before anything happens
    service.start(run_id)
    await wait_for(lambda: service.get_run(run_id).status == "waiting_for_approval")
    service.resolve_approval(run_id, service.get_run(run_id).approvals[0].id, "approve")
    await asyncio.wait_for(consumer, 2)  # the stream ends by itself when the run ends

    assert [e.id for e in received] == list(range(1, len(received) + 1))
    t1 = [e.type for e in received if e.task_id == "t1"]
    assert t1 == ["task.started", "task.completed"]
    assert received[-1].type == "run.completed"


async def test_disconnecting_does_not_stop_the_run() -> None:
    service = make_service()
    run_id = await new_run(service)
    service.start(run_id)

    stream = service.follow(run_id)
    first = await anext(stream)
    assert first.type == "run.started"
    await stream.aclose()  # client went away

    await wait_for(lambda: service.get_run(run_id).status == "waiting_for_approval")
    assert service.get_run(run_id).tasks[3].status == "completed"


async def test_many_consumers_get_the_same_events() -> None:
    service = make_service()
    run_id = await new_run(service)

    async def collect() -> list[int]:
        return [e.id async for e in service.follow(run_id) if e]

    consumers = [asyncio.create_task(collect()) for _ in range(3)]
    await asyncio.sleep(0)
    service.start(run_id)
    await asyncio.sleep(0.01)
    service.cancel(run_id)
    results = await asyncio.wait_for(asyncio.gather(*consumers), 2)
    assert results[0] == results[1] == results[2]
    assert len(results[0]) == service.get_run(run_id).last_event_id


async def test_idle_stream_sends_heartbeats() -> None:
    service = make_service()
    run_id = await new_run(service)
    service.start(run_id)
    await wait_for(lambda: service.get_run(run_id).status == "waiting_for_approval")

    stream = service.follow(run_id, after_id=service.get_run(run_id).last_event_id, heartbeat_seconds=0.01)
    assert await asyncio.wait_for(anext(stream), 1) is None  # nothing new: a heartbeat
    await stream.aclose()


async def test_completed_runs_stay_retrievable() -> None:
    service = make_service()
    run_id = await new_run(service)
    service.start(run_id)
    service.cancel(run_id)
    snapshot = service.get_run(run_id)
    replay = [e async for e in service.follow(run_id)]
    assert snapshot.status == "cancelled"
    assert replay[-1].id == snapshot.last_event_id


async def test_shutdown_cancels_unfinished_runs() -> None:
    service = make_service(scale=1.0)
    run_id = await new_run(service)
    service.start(run_id)
    await service.shutdown()
    assert service.get_run(run_id).status == "cancelled"
