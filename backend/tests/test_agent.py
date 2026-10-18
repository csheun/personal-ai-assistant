import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.service import AgentService, IterationLimitError, LLMUpstreamError
from app.tools import build_default_registry
from tests.fakes import ScriptedChatModel, tool_call


def make_agent(llm: ScriptedChatModel, max_iterations: int = 5) -> AgentService:
    return AgentService(llm, build_default_registry(), max_iterations=max_iterations, model_name="fake")


async def test_direct_answer_without_tools() -> None:
    llm = ScriptedChatModel(responses=[AIMessage("Hello!")])
    run = await make_agent(llm).run("hi")

    assert run.answer == "Hello!"
    assert run.tool_results == []
    assert run.iterations == 1
    assert {t["function"]["name"] for t in llm.bound_tools} == {"get_weather", "web_search"}


async def test_llm_chooses_tool_and_receives_result() -> None:
    llm = ScriptedChatModel(
        responses=[
            AIMessage("", tool_calls=[tool_call("get_weather", {"city": "Singapore"})]),
            AIMessage("It's simulated, but Singapore looks warm."),
        ]
    )
    run = await make_agent(llm).run("Weather in Singapore?")

    assert run.answer == "It's simulated, but Singapore looks warm."
    assert run.iterations == 2
    [result] = run.tool_results
    assert result.tool_name == "get_weather" and result.ok and result.mocked

    # The second LLM call must include the tool's output, linked to the right call id.
    tool_msg = llm.received[1][-1]
    assert isinstance(tool_msg, ToolMessage)
    assert tool_msg.tool_call_id == "call_1"
    assert json.loads(tool_msg.content)["output"]["city"] == "Singapore"


async def test_parallel_tool_calls_in_one_turn() -> None:
    llm = ScriptedChatModel(
        responses=[
            AIMessage(
                "",
                tool_calls=[
                    tool_call("get_weather", {"city": "Tokyo"}, "a"),
                    tool_call("web_search", {"query": "Tokyo events"}, "b"),
                ],
            ),
            AIMessage("Done."),
        ]
    )
    run = await make_agent(llm).run("Plan my Tokyo day")

    assert [r.tool_name for r in run.tool_results] == ["get_weather", "web_search"]
    assert [m.tool_call_id for m in llm.received[1][-2:]] == ["a", "b"]


async def test_invalid_tool_args_are_returned_to_llm_as_error() -> None:
    llm = ScriptedChatModel(
        responses=[
            AIMessage("", tool_calls=[tool_call("get_weather", {"town": "Oslo"})]),
            AIMessage("", tool_calls=[tool_call("get_weather", {"city": "Oslo"}, "call_2")]),
            AIMessage("Oslo is (mock) chilly."),
        ]
    )
    run = await make_agent(llm).run("Weather in Oslo")

    first, second = run.tool_results
    assert not first.ok and first.error.code == "invalid_arguments"
    assert second.ok
    error_msg = llm.received[1][-1]
    assert error_msg.status == "error"


async def test_unknown_tool_is_not_executed() -> None:
    llm = ScriptedChatModel(
        responses=[
            AIMessage("", tool_calls=[tool_call("run_shell", {"cmd": "rm -rf /"})]),
            AIMessage("I can't do that."),
        ]
    )
    run = await make_agent(llm).run("delete files")

    assert run.tool_results[0].error.code == "unknown_tool"


async def test_malformed_json_tool_call_is_answered() -> None:
    bad = AIMessage(
        "",
        invalid_tool_calls=[{"name": "get_weather", "args": "{city:", "id": "bad_1", "error": "bad json", "type": "invalid_tool_call"}],
    )
    llm = ScriptedChatModel(responses=[bad, AIMessage("Sorry, try again.")])
    run = await make_agent(llm).run("weather")

    assert run.tool_results[0].error.code == "invalid_arguments"
    assert llm.received[1][-1].tool_call_id == "bad_1"


async def test_iteration_limit() -> None:
    looping = [AIMessage("", tool_calls=[tool_call("web_search", {"query": "x"}, f"c{i}")]) for i in range(3)]
    llm = ScriptedChatModel(responses=looping)

    with pytest.raises(IterationLimitError):
        await make_agent(llm, max_iterations=2).run("loop forever")


async def test_llm_failure_becomes_upstream_error() -> None:
    llm = ScriptedChatModel(responses=[])  # raises on first call
    with pytest.raises(LLMUpstreamError):
        await make_agent(llm).run("hi")
