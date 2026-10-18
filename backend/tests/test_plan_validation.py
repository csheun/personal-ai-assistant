import pytest

from app.workflows.plan_schema import PlannerOutput
from app.workflows.validation import PlanLimits, ValidAnswer, ValidPlan, validate_plan
from tests.planning_helpers import DEMO_PLAN, planner_tools, task, workflow


def check(data: dict, limits: PlanLimits = PlanLimits()):  # type: ignore[no-untyped-def]
    return validate_plan(PlannerOutput.model_validate(data), planner_tools(), limits)


def errors_of(data: dict, limits: PlanLimits = PlanLimits()) -> str:
    result = check(data, limits)
    assert isinstance(result, list), f"expected errors, got {result}"
    return "\n".join(result)


def test_demo_plan_is_valid_and_approval_comes_from_the_tool() -> None:
    plan = check(DEMO_PLAN)
    assert isinstance(plan, ValidPlan)
    assert [t.requires_approval for t in plan.tasks] == [False, False, False, True]
    assert plan.tasks[2].depends_on == ["t1", "t2"]


def test_llm_cannot_switch_approval_off() -> None:
    data = workflow(*DEMO_PLAN["tasks"][:3], {**DEMO_PLAN["tasks"][3], "requires_approval": False})
    plan = check(data)
    assert isinstance(plan, ValidPlan) and plan.tasks[3].requires_approval is True


def test_direct_answer() -> None:
    assert check({"mode": "answer", "answer": " 4 "}) == ValidAnswer("4")
    assert "empty" in errors_of({"mode": "answer", "answer": ""})
    assert "must be empty" in errors_of({"mode": "answer", "answer": "x", "tasks": [task("t1", "web_search", {"query": "x"})]})


SUMMARY = task("s", "summarize", {}, ["t1"])
SEARCH = task("t1", "web_search", {"query": "x"})


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (workflow(task("t1", "run_shell", {"cmd": "rm"}), SUMMARY), 'unknown tool "run_shell"'),
        (workflow(SEARCH, task("t1", "web_search", {"query": "y"}), SUMMARY), "more than once"),
        (workflow(task("bad id!", "web_search", {"query": "x"}), task("s", "summarize", {}, ["bad id!"])), "invalid"),
        (workflow(SEARCH, task("s", "summarize", {}, ["t1", "t9"])), '"t9", which is not in the plan'),
        (workflow(task("t1", "web_search", {"query": "x"}, ["t1"]), SUMMARY), "depends on itself"),
        (workflow(task("t1", "web_search", {"query": "x", "max_results": 50}), SUMMARY), "max_results"),
        (workflow(task("t1", "web_search", {}), SUMMARY), "query"),
        (workflow(task("t1", "web_search", {"query": "x", "extra": 1}), SUMMARY), "extra"),
        (workflow(SEARCH, task("s", "summarize", {"sources": [{"tool_name": "x", "output": {}}]}, ["t1"])), 'do not set "sources"'),
        (workflow(SEARCH, SUMMARY, task("tg", "telegram_send_message", {"text": "hi"}, ["s"])), 'do not set "text"'),
        (workflow(SEARCH), 'exactly one "summarize"'),
        (workflow(SEARCH, SUMMARY, task("s2", "summarize", {}, ["t1"])), "found 2"),
        (workflow(SEARCH, task("s", "summarize", {}, [])), "must depend on the data tasks"),
        (workflow(SEARCH, task("t2", "get_weather", {"city": "Oslo"}), SUMMARY), 'must depend on data task "t2"'),
        (workflow(SEARCH, SUMMARY, task("tg", "telegram_send_message", {}, ["t1"])), "must depend only on"),
        (workflow(SEARCH, SUMMARY, task("t2", "web_search", {"query": "y"}, ["s"])), "cannot depend on"),
        ({"mode": "workflow", "goal": "g", "tasks": [SEARCH, SUMMARY]}, '"reply" is required'),
        (workflow(), "at least one task"),
    ],
)
def test_invalid_plans_are_rejected_with_actionable_errors(data: dict, expected: str) -> None:
    assert expected in errors_of(data)


def test_cycle() -> None:
    data = workflow(
        task("a", "web_search", {"query": "x"}, ["b"]),
        task("b", "web_search", {"query": "y"}, ["a"]),
        task("s", "summarize", {}, ["a", "b"]),
    )
    assert "cycle" in errors_of(data)


def test_task_count_and_depth_limits() -> None:
    many = workflow(*[task(f"t{i}", "web_search", {"query": "x"}) for i in range(8)], task("s", "summarize", {}, [f"t{i}" for i in range(8)]))
    assert "Too many tasks (9)" in errors_of(many)

    chain = [task("t0", "web_search", {"query": "x"})] + [
        task(f"t{i}", "web_search", {"query": "x"}, [f"t{i - 1}"]) for i in range(1, 4)
    ]
    deep = workflow(*chain, task("s", "summarize", {}, [t["id"] for t in chain]))
    assert "5 steps deep" in errors_of(deep)


def test_disallowed_risk_levels() -> None:
    read_only = PlanLimits(allowed_risks=frozenset({"read"}))
    assert 'Tool "telegram_send_message" is not allowed' in errors_of(DEMO_PLAN, read_only)
