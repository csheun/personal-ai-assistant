import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.service import AgentService
from app.main import create_app
from app.tools import build_default_registry
from tests.fakes import ScriptedChatModel, tool_call


def client_with(responses: list[AIMessage], max_iterations: int = 5) -> TestClient:
    agent = AgentService(
        ScriptedChatModel(responses=responses), build_default_registry(), max_iterations, model_name="fake:test"
    )
    return TestClient(create_app(agent=agent))


def test_health() -> None:
    with client_with([]) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_with_tool_call() -> None:
    responses = [
        AIMessage("", tool_calls=[tool_call("get_weather", {"city": "Singapore", "unit": "fahrenheit"})]),
        AIMessage("(Simulated) It's warm in Singapore."),
    ]
    with client_with(responses) as client:
        response = client.post("/api/chat", json={"message": "Weather in Singapore?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "(Simulated) It's warm in Singapore."
    assert body["model"] == "fake:test"
    assert body["iterations"] == 2
    [call] = body["tool_calls"]
    assert call["tool_name"] == "get_weather"
    assert call["ok"] is True and call["mocked"] is True
    assert call["output"]["unit"] == "fahrenheit"


def test_chat_without_tools() -> None:
    with client_with([AIMessage("Hi there!")]) as client:
        response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["tool_calls"] == []


@pytest.mark.parametrize(
    "payload",
    [{}, {"message": ""}, {"message": "   "}, {"message": "x" * 4001}, {"message": 42}, {"message": "hi", "extra": 1}],
)
def test_chat_rejects_invalid_requests(payload: dict) -> None:
    with client_with([]) as client:
        response = client.post("/api/chat", json=payload)
    assert response.status_code == 422


def test_chat_llm_failure_returns_502_without_leaking_details() -> None:
    with client_with([]) as client:  # fake LLM raises on first call
        response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert "ScriptedChatModel" not in response.text


def test_chat_iteration_limit_returns_500() -> None:
    looping = [AIMessage("", tool_calls=[tool_call("web_search", {"query": "x"}, f"c{i}")]) for i in range(2)]
    with client_with(looping, max_iterations=1) as client:
        response = client.post("/api/chat", json={"message": "loop"})
    assert response.status_code == 500
