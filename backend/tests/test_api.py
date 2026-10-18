import json
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BRIEFING = "Give me a morning briefing and send it to Telegram"


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(mock_latency_scale=0.01, sse_heartbeat_seconds=0.05, llm_api_key=None)
    with TestClient(create_app(settings)) as c:
        yield c


def start_briefing(client: TestClient, message: str = BRIEFING) -> dict:
    response = client.post("/api/chat", json={"message": message})
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    assert client.post(f"/api/workflows/{run['id']}/start").status_code == 200
    return run


def wait_for_status(client: TestClient, run_id: str, *statuses: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/workflows/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.005)
    raise AssertionError(f"run {run_id} never reached {statuses}; last status {run['status']}")


def read_sse(client: TestClient, url: str, headers: dict | None = None) -> list[dict]:
    """Reads an SSE stream to the end and returns the parsed `data` payloads."""
    events, data = [], []
    with client.stream("GET", url, headers=headers or {}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data:"):
                data.append(line[5:].strip())
            elif line == "" and data:
                events.append(json.loads("\n".join(data)))
                data = []
    return events


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_creates_conversation_and_planned_run(client: TestClient) -> None:
    body = client.post("/api/chat", json={"message": BRIEFING}).json()

    run = body["run"]
    assert run["status"] == "planned"
    assert run["last_event_id"] == 0
    assert [t["id"] for t in run["tasks"]] == ["t1", "t2", "t3", "t4", "t5"]
    assert run["tasks"][3]["depends_on"] == ["t1", "t2", "t3"]
    assert run["tasks"][4]["requires_approval"] is True
    assert body["assistant_message"]["run_id"] == run["id"]

    conversation_id = body["conversation"]["id"]
    assert [c["id"] for c in client.get("/api/conversations").json()] == [conversation_id]
    assert len(client.get(f"/api/conversations/{conversation_id}/messages").json()) == 2
    # Nothing runs until started.
    time.sleep(0.05)
    assert client.get(f"/api/workflows/{run['id']}").json()["status"] == "planned"


def test_message_without_tools_gets_a_direct_reply(client: TestClient) -> None:
    body = client.post("/api/chat", json={"message": "hello"}).json()
    assert body["run"] is None
    assert body["assistant_message"]["content"]


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"message": ""}, 422),
        ({"message": "x" * 4001}, 422),
        ({"message": "hi", "extra": 1}, 422),
        ({"message": "simulate error"}, 503),
        ({"message": "hi", "conversation_id": "conv_missing"}, 404),
    ],
)
def test_chat_errors(client: TestClient, payload: dict, status: int) -> None:
    response = client.post("/api/chat", json=payload)
    assert response.status_code == status
    assert "detail" in response.json()


def test_full_run_over_http_and_sse(client: TestClient) -> None:
    run = start_briefing(client)
    waiting = wait_for_status(client, run["id"], "waiting_for_approval")
    approval = waiting["approvals"][0]
    assert approval["preview"]["body"].startswith("Singapore:")

    response = client.post(
        f"/api/workflows/{run['id']}/approve", json={"approval_id": approval["id"], "decision": "approve"}
    )
    assert response.json()["status"] == "approved"
    final = wait_for_status(client, run["id"], "completed")

    events = read_sse(client, f"/api/workflows/{run['id']}/events")
    assert [e["id"] for e in events] == list(range(1, final["last_event_id"] + 1))
    assert all(e["run_id"] == run["id"] for e in events)
    assert events[0]["type"] == "run.started"
    assert events[-1]["type"] == "run.completed"
    # Status transitions per task, in order.
    t5 = [e["type"] for e in events if e["task_id"] == "t5"]
    assert t5 == ["approval.requested", "approval.resolved", "task.started", "task.completed"]
    t4_started = next(e["id"] for e in events if e["type"] == "task.started" and e["task_id"] == "t4")
    step1_done = [e["id"] for e in events if e["type"] == "task.completed" and e["task_id"] in {"t1", "t2", "t3"}]
    assert t4_started > max(step1_done)
    # Every tool result is mocked: nothing real ran.
    assert all(e["data"]["result"]["mocked"] for e in events if e["type"] == "task.completed")


def test_stream_resumes_after_last_event_id(client: TestClient) -> None:
    run = start_briefing(client)
    snapshot = wait_for_status(client, run["id"], "waiting_for_approval")
    resume_at = snapshot["last_event_id"]

    approval_id = snapshot["approvals"][0]["id"]
    client.post(f"/api/workflows/{run['id']}/approve", json={"approval_id": approval_id, "decision": "approve"})
    wait_for_status(client, run["id"], "completed")

    by_header = read_sse(client, f"/api/workflows/{run['id']}/events", headers={"Last-Event-ID": str(resume_at)})
    by_query = read_sse(client, f"/api/workflows/{run['id']}/events?after={resume_at}")
    assert by_header == by_query
    assert by_header[0]["id"] == resume_at + 1
    assert by_header[0]["type"] == "approval.resolved"
    # On reconnect the browser keeps the original ?after= but sends a newer Last-Event-ID: the header wins.
    reconnect = read_sse(
        client, f"/api/workflows/{run['id']}/events?after=0", headers={"Last-Event-ID": str(resume_at)}
    )
    assert reconnect == by_header


def test_reject(client: TestClient) -> None:
    run = start_briefing(client)
    approval = wait_for_status(client, run["id"], "waiting_for_approval")["approvals"][0]
    client.post(f"/api/workflows/{run['id']}/approve", json={"approval_id": approval["id"], "decision": "reject"})
    final = wait_for_status(client, run["id"], "completed")
    assert final["tasks"][4]["status"] == "skipped"

    again = client.post(f"/api/workflows/{run['id']}/approve", json={"approval_id": approval["id"], "decision": "approve"})
    assert again.status_code == 409


def test_cancel(client: TestClient) -> None:
    run = start_briefing(client)
    response = client.post(f"/api/workflows/{run['id']}/cancel")
    assert response.json()["status"] == "cancelled"
    assert client.post(f"/api/workflows/{run['id']}/cancel").status_code == 409
    events = read_sse(client, f"/api/workflows/{run['id']}/events")
    assert events[-1]["type"] == "run.cancelled"


def test_failure_scenario(client: TestClient) -> None:
    run = start_briefing(client, "Check the weather in Oslo and simulate failure")
    final = wait_for_status(client, run["id"], "failed")
    assert [t["status"] for t in final["tasks"]] == ["failed", "skipped"]


def test_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/api/workflows/run_missing").status_code == 404
    assert client.get("/api/workflows/run_missing/events").status_code == 404
    assert client.post("/api/workflows/run_missing/start").status_code == 404


def test_simultaneous_runs_stay_isolated(client: TestClient) -> None:
    a = start_briefing(client)
    b = start_briefing(client)
    assert a["id"] != b["id"] and a["conversation_id"] != b["conversation_id"]

    wait_for_status(client, b["id"], "waiting_for_approval")
    client.post(f"/api/workflows/{b['id']}/cancel")
    approval = wait_for_status(client, a["id"], "waiting_for_approval")["approvals"][0]
    client.post(f"/api/workflows/{a['id']}/approve", json={"approval_id": approval["id"], "decision": "approve"})

    assert wait_for_status(client, a["id"], "completed")["status"] == "completed"
    assert client.get(f"/api/workflows/{b['id']}").json()["status"] == "cancelled"
    a_events = read_sse(client, f"/api/workflows/{a['id']}/events")
    assert {e["run_id"] for e in a_events} == {a["id"]}
    assert a_events[0]["id"] == 1
    # Approvals belong to their own run.
    wrong_run = client.post(f"/api/workflows/{b['id']}/approve", json={"approval_id": approval["id"], "decision": "approve"})
    assert wrong_run.status_code == 404

    stats = client.get("/api/stats").json()
    assert stats["total_runs"] == 2 and stats["completed_runs"] == 1 and stats["cancelled_runs"] == 1


def test_cors_allows_the_frontend(client: TestClient) -> None:
    response = client.options(
        "/api/chat", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
