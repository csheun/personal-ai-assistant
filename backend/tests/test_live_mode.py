"""MOCK_MODE=false through the real HTTP API, with only the edges faked:
a scripted LLM (planner + synthesizer) and httpx.MockTransport (Open-Meteo, Tavily).
Validation, bindings, the runner, the registry and SSE are the real code."""

import json
from collections.abc import Iterator
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.config import Settings
from app.llm.provider import LLMConfigError
from app.main import create_app
from app.providers.open_meteo import GEOCODING_URL
from app.providers.tavily import SEARCH_URL
from tests.fakes import fake_llm, structured
from tests.http_fakes import FORECAST, SINGAPORE
from tests.planning_helpers import task, workflow
from tests.test_api import read_sse, wait_for_status

TOMORROW = (datetime.now().astimezone().date() + timedelta(days=1)).isoformat()
NEWS = {"results": [{"title": "Model A ships", "url": "https://news.example/a", "content": "A new model.", "published_date": "2026-10-18"}]}

WEATHER = task("t1", "get_weather", {"location": "Singapore", "start_date": TOMORROW})
SEARCH = task("t2", "web_search", {"query": "AI news", "topic": "news", "time_range": "week"})


def plan(*tasks: dict) -> AIMessage:
    return structured("PlannerOutput", workflow(*tasks))


def synthesis(text: str, refs: list[int] | None = None) -> AIMessage:
    return structured("_SynthesisDraft", {"text": text, "cited_refs": refs or []})


def providers(weather_status: int = 200) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        url = str(request.url)
        if url.startswith(GEOCODING_URL):
            return httpx.Response(200, json={"results": [SINGAPORE]})
        if url.startswith(SEARCH_URL):
            return httpx.Response(200, json=NEWS)
        return httpx.Response(weather_status, json=FORECAST if weather_status == 200 else {})

    return httpx.MockTransport(handler), seen


def live_client(*llm_responses: AIMessage, weather_status: int = 200, **settings: object):  # type: ignore[no-untyped-def]
    llm, model = fake_llm(*llm_responses)
    transport, seen = providers(weather_status)
    defaults: dict[str, object] = {
        "mock_mode": False,
        "groq_api_key": "test",
        "web_search_api_key": "tvly-test",
        "sse_heartbeat_seconds": 0.05,
    }
    config = Settings(_env_file=None, **{**defaults, **settings})  # type: ignore[call-arg, arg-type]
    return TestClient(create_app(config, llm=llm, http_transport=transport)), model, seen


def chat(client: TestClient, message: str) -> dict:
    response = client.post("/api/chat", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def run_to_end(client: TestClient, run_id: str, approve: bool | None = None) -> dict:
    assert client.post(f"/api/workflows/{run_id}/start").status_code == 200
    if approve is not None:
        approval = wait_for_status(client, run_id, "waiting_for_approval")["approvals"][0]
        decision = "approve" if approve else "reject"
        client.post(f"/api/workflows/{run_id}/approve", json={"approval_id": approval["id"], "decision": decision})
    return wait_for_status(client, run_id, "completed", "failed")


def test_general_question_is_answered_directly() -> None:
    client, model, seen = live_client(structured("PlannerOutput", {"mode": "answer", "answer": "A DAG is a graph with no cycles."}))
    with client:
        body = chat(client, "What is a DAG?")
    assert body["run"] is None
    assert body["assistant_message"]["content"] == "A DAG is a graph with no cycles."
    planning = body["assistant_message"]["planning"]
    assert planning["planner"] == "llm" and planning["usage"][0]["input_tokens"] == 100
    assert seen == []  # no tools, no provider calls


def test_weather_only_request() -> None:
    client, model, seen = live_client(
        plan(WEATHER, task("t2", "summarize", {"instruction": "One sentence."}, ["t1"])),
        synthesis("Tomorrow: thunderstorms, 25-32°C."),
    )
    with client:
        body = chat(client, "Weather in Singapore tomorrow?")
        run = body["run"]
        assert [t["tool_name"] for t in run["tasks"]] == ["get_weather", "summarize"]
        assert run["planning"]["planner"] == "llm"
        final = run_to_end(client, run["id"])

    assert final["status"] == "completed"
    assert final["summary"] == "Tomorrow: thunderstorms, 25-32°C."
    assert final["tasks"][0]["result"]["output"]["daily"][0]["condition"] == "Thunderstorm"
    # The synthesizer received the real tool output, fenced as data.
    synth_prompt = model.received[1][-1].content
    assert "<data>" in synth_prompt and "Thunderstorm" in synth_prompt
    assert not any(str(r.url).startswith(SEARCH_URL) for r in seen)


def test_search_only_request_keeps_citations() -> None:
    client, _, _ = live_client(
        plan(task("t1", "web_search", {"query": "AI news"}), task("t2", "summarize", {}, ["t1"])),
        synthesis("Model A shipped [1].", refs=[1]),
    )
    with client:
        final = run_to_end(client, chat(client, "Latest AI news?")["run"]["id"])
    summary_output = final["tasks"][1]["result"]["output"]
    assert summary_output["sources"] == [{"ref": 1, "title": "Model A ships", "url": "https://news.example/a"}]
    assert summary_output["usage"]["purpose"] == "synthesize"


def test_demo_flow_runs_tools_concurrently_and_sends_only_after_approval() -> None:
    client, _, _ = live_client(
        plan(WEATHER, SEARCH, task("t3", "summarize", {"instruction": "Summarize both."}, ["t1", "t2"]),
             task("t4", "telegram_send_message", {}, ["t3"])),
        synthesis("Storms tomorrow. Model A shipped [1].", refs=[1]),
    )  # fmt: skip
    with client:
        run = chat(client, "Check tomorrow's weather in Singapore, search for recent AI news, summarize both, and send it to Telegram.")["run"]
        assert run["tasks"][3]["requires_approval"] is True
        client.post(f"/api/workflows/{run['id']}/start")
        waiting = wait_for_status(client, run["id"], "waiting_for_approval")

        # The approval shows exactly the synthesized text.
        approval = waiting["approvals"][0]
        assert approval["preview"]["body"] == "Storms tomorrow. Model A shipped [1]."
        assert waiting["tasks"][3]["status"] == "waiting_for_approval" and waiting["tasks"][3]["started_at"] is None

        client.post(f"/api/workflows/{run['id']}/approve", json={"approval_id": approval["id"], "decision": "approve"})
        final = wait_for_status(client, run["id"], "completed")
        events = read_sse(client, f"/api/workflows/{run['id']}/events")

    t1, t2, t3, t4 = final["tasks"]
    starts = [datetime.fromisoformat(t["started_at"]) for t in (t1, t2)]
    assert abs((starts[0] - starts[1]).total_seconds()) < 0.05  # weather and search started together
    assert t3["started_at"] >= max(t1["finished_at"], t2["finished_at"])  # summary waited for both
    assert t4["result"]["arguments"]["text"] == "Storms tomorrow. Model A shipped [1]."
    order = [(e["type"], e["task_id"]) for e in events]
    assert order.index(("approval.resolved", "t4")) < order.index(("task.started", "t4"))


def test_rejected_approval_skips_the_send() -> None:
    client, _, _ = live_client(
        plan(SEARCH, task("t3", "summarize", {}, ["t2"]), task("t4", "telegram_send_message", {}, ["t3"])),
        synthesis("News."),
    )
    with client:
        final = run_to_end(client, chat(client, "News to Telegram")["run"]["id"], approve=False)
    assert final["status"] == "completed" and final["tasks"][2]["status"] == "skipped"


def test_tool_failure_skips_the_summary_and_fails_the_run() -> None:
    client, _, _ = live_client(plan(WEATHER, task("t2", "summarize", {}, ["t1"])), weather_status=503)
    with client:
        final = run_to_end(client, chat(client, "Weather?")["run"]["id"])
    assert final["status"] == "failed"
    weather, summary = final["tasks"]
    assert weather["result"]["error"]["code"] == "provider_error" and "503" in weather["status_reason"]
    assert summary["status"] == "skipped"


def test_invalid_plan_is_never_executed() -> None:
    bad = structured("PlannerOutput", workflow(task("t1", "run_shell", {"cmd": "rm -rf /"})))
    client, model, seen = live_client(bad, bad)
    with client:
        response = client.post("/api/chat", json={"message": "delete everything"})
        assert response.status_code == 502
        assert "couldn't build a valid plan" in response.json()["detail"]
        assert client.get("/api/conversations").json() == []  # nothing stored
    assert len(model.received) == 2 and seen == []


def test_llm_outage_is_503() -> None:
    client, _, _ = live_client()  # the fake LLM has no responses: the call fails
    with client:
        response = client.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 503 and "AI service" in response.json()["detail"]


def test_capabilities_report_live_tools_without_secrets() -> None:
    client, _, _ = live_client()
    with client:
        caps = client.get("/api/capabilities").json()
    assert caps["mode"] == "live" and caps["llm_model"] == "groq:openai/gpt-oss-120b"
    assert {t["name"]: t["mocked"] for t in caps["tools"]} == {
        "get_weather": False, "web_search": False, "summarize": False, "telegram_send_message": True,
    }  # fmt: skip
    assert "tvly-test" not in json.dumps(caps)


def test_web_search_is_unavailable_without_its_key() -> None:
    client, _, _ = live_client(web_search_api_key=None)
    with client:
        names = [t["name"] for t in client.get("/api/capabilities").json()["tools"]]
    assert "web_search" not in names and "get_weather" in names


def test_live_mode_without_llm_key_fails_at_startup() -> None:
    config = Settings(_env_file=None, mock_mode=False, groq_api_key=None)  # type: ignore[call-arg]
    with pytest.raises(LLMConfigError, match="GROQ_API_KEY"):
        with TestClient(create_app(config)):
            pass


def test_mock_mode_still_works_by_default() -> None:
    with TestClient(create_app(Settings(_env_file=None, mock_latency_scale=0))) as client:  # type: ignore[call-arg]
        assert client.get("/api/capabilities").json()["mode"] == "mock"
        body = chat(client, "Give me a morning briefing and send it to Telegram")
        assert body["run"]["planning"]["planner"] == "mock"
