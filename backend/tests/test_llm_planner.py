from datetime import date

import pytest
from langchain_core.messages import AIMessage

from app.llm.client import LLMUnavailable
from app.workflows.llm_planner import LLMPlanner, PlanningFailed
from app.workflows.validation import ValidAnswer, ValidPlan
from tests.fakes import fake_llm, structured
from tests.planning_helpers import DEMO_PLAN, planner_tools, task, workflow

TODAY = date(2026, 10, 18)


def planner(*responses: AIMessage, max_attempts: int = 2):  # type: ignore[no-untyped-def]
    llm, model = fake_llm(*responses)
    return LLMPlanner(llm, planner_tools(), max_attempts=max_attempts), model


async def test_general_question_gets_a_direct_answer() -> None:
    p, _ = planner(structured("PlannerOutput", {"mode": "answer", "answer": "Paris is the capital of France."}))
    result, report = await p.plan("What's the capital of France?", today=TODAY)
    assert result == ValidAnswer("Paris is the capital of France.")
    assert report.attempts == 1 and report.usage[0].purpose == "plan"


async def test_demo_request_becomes_a_validated_plan() -> None:
    p, model = planner(structured("PlannerOutput", DEMO_PLAN))
    result, report = await p.plan("Weather tomorrow in Singapore, AI news, summarize, send to Telegram", today=TODAY)

    assert isinstance(result, ValidPlan)
    assert [t.tool_name for t in result.tasks] == ["get_weather", "web_search", "summarize", "telegram_send_message"]
    assert result.tasks[3].requires_approval is True
    # The prompt gives the model today's date and the tool catalog, without bound fields.
    system = model.received[0][0].content
    assert "Today is Sunday 2026-10-18" in system
    assert "Saturday 2026-10-24" in system  # dates are given, not computed by the model
    assert '"get_weather"' in system and '"filled_automatically"' in system
    assert '"sources": {' not in system


async def test_invalid_plan_is_repaired_once_with_the_errors() -> None:
    bad = workflow(task("t1", "run_shell", {"cmd": "ls"}), task("s", "summarize", {}, ["t1"]))
    p, model = planner(structured("PlannerOutput", bad), structured("PlannerOutput", DEMO_PLAN))

    result, report = await p.plan("weather and news", today=TODAY)

    assert isinstance(result, ValidPlan)
    assert report.attempts == 2 and len(report.usage) == 2
    repair_prompt = model.received[1][-1].content
    assert 'unknown tool "run_shell"' in repair_prompt
    assert "run_shell" in model.received[1][-2].content  # the model sees its own rejected draft


async def test_gives_up_after_max_attempts_without_executing_anything() -> None:
    bad = workflow(task("t1", "web_search", {"query": "x"}))  # no summary
    p, model = planner(structured("PlannerOutput", bad), structured("PlannerOutput", bad))
    with pytest.raises(PlanningFailed) as caught:
        await p.plan("news", today=TODAY)
    assert 'exactly one "summarize"' in caught.value.errors[0]
    assert len(model.received) == 2  # bounded: never a third call


async def test_unparseable_output_counts_as_an_attempt_and_is_repaired() -> None:
    p, _ = planner(AIMessage("Sure! Here's my plan..."), structured("PlannerOutput", DEMO_PLAN))
    result, report = await p.plan("news", today=TODAY)
    assert isinstance(result, ValidPlan) and report.attempts == 2


async def test_provider_outage_is_not_retried_by_the_planner() -> None:
    p, _ = planner()  # the fake raises on the first call
    with pytest.raises(LLMUnavailable):
        await p.plan("news", today=TODAY)


async def test_single_attempt_mode() -> None:
    bad = workflow(task("t1", "web_search", {"query": "x"}))
    p, model = planner(structured("PlannerOutput", bad), max_attempts=1)
    with pytest.raises(PlanningFailed):
        await p.plan("news", today=TODAY)
    assert len(model.received) == 1
