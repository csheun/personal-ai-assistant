"""Checks an LLM-drafted plan before anything executes. Nothing unvalidated reaches the runner.

Every rule produces a plain-English error. The planner sends these back to the LLM for one
repair attempt, so the messages are written to be actionable by a model as well as a human.

What the LLM is *not* trusted with, regardless of what it writes:
- `requires_approval` is derived from each tool's risk level, never read from the plan.
- Fields the backend fills from upstream results (`Tool.bound_inputs`) may not be set.
- Which tools exist: anything outside the registry is rejected.
"""

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.tools import ToolRegistry
from app.workflows.graph import InvalidWorkflowError, dependency_levels
from app.workflows.models import WorkflowTask
from app.workflows.plan_schema import PlannerOutput

SYNTHESIS_TOOL = "summarize"
_ID = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


@dataclass(frozen=True)
class PlanLimits:
    max_tasks: int = 8
    max_depth: int = 4
    allowed_risks: frozenset[str] = frozenset({"read", "external_write"})


@dataclass(frozen=True)
class ValidPlan:
    reply: str
    goal: str
    tasks: list[WorkflowTask]


@dataclass(frozen=True)
class ValidAnswer:
    answer: str


@dataclass
class _Errors:
    items: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.items.append(message)


def validate_plan(draft: PlannerOutput, tools: ToolRegistry, limits: PlanLimits = PlanLimits()) -> ValidPlan | ValidAnswer | list[str]:
    """Returns the validated plan/answer, or the list of everything wrong with it."""
    errors = _Errors()

    if draft.mode == "answer":
        if not (draft.answer and draft.answer.strip()):
            errors.add('mode is "answer" but "answer" is empty.')
        if draft.tasks:
            errors.add('mode is "answer", so "tasks" must be empty.')
        return errors.items or ValidAnswer(draft.answer.strip())  # type: ignore[union-attr]

    if not (draft.reply and draft.reply.strip()):
        errors.add('"reply" is required for a workflow.')
    if not (draft.goal and draft.goal.strip()):
        errors.add('"goal" is required for a workflow.')
    if not draft.tasks:
        errors.add("A workflow needs at least one task.")
        return errors.items
    if len(draft.tasks) > limits.max_tasks:
        errors.add(f"Too many tasks ({len(draft.tasks)}); the maximum is {limits.max_tasks}.")

    ids = [t.id for t in draft.tasks]
    for task_id in {i for i in ids if ids.count(i) > 1}:
        errors.add(f'Task id "{task_id}" is used more than once; ids must be unique.')
    for task in draft.tasks:
        if not _ID.match(task.id):
            errors.add(f'Task id "{task.id}" is invalid; use 1-20 letters, digits, "_" or "-".')
        if not task.title.strip():
            errors.add(f'Task "{task.id}" needs a title.')
        _check_tool_and_arguments(task, tools, limits, errors)
        for dep in task.depends_on:
            if dep == task.id:
                errors.add(f'Task "{task.id}" depends on itself.')
            elif dep not in ids:
                errors.add(f'Task "{task.id}" depends on "{dep}", which is not in the plan.')

    if errors.items:
        return errors.items  # structure is broken; graph checks would only add noise

    tasks = [_to_workflow_task(t, tools) for t in draft.tasks]
    try:
        levels = dependency_levels(tasks)
    except InvalidWorkflowError:
        errors.add("The dependencies form a cycle; a task cannot (indirectly) depend on itself.")
        return errors.items
    if max(levels.values()) + 1 > limits.max_depth:
        errors.add(f"The plan is {max(levels.values()) + 1} steps deep; the maximum is {limits.max_depth}.")

    _check_shape(draft, tools, errors)
    return errors.items or ValidPlan(reply=draft.reply.strip(), goal=draft.goal.strip(), tasks=tasks)  # type: ignore[union-attr]


def _check_tool_and_arguments(task, tools: ToolRegistry, limits: PlanLimits, errors: _Errors) -> None:  # type: ignore[no-untyped-def]
    tool = tools.get(task.tool)
    if tool is None:
        errors.add(f'Task "{task.id}" uses unknown tool "{task.tool}". Available: {", ".join(tools.names)}.')
        return
    if tool.risk not in limits.allowed_risks:
        errors.add(f'Tool "{tool.name}" is not allowed in plans.')
    for name in sorted(tool.bound_inputs & task.arguments.keys()):
        errors.add(f'Task "{task.id}": do not set "{name}"; it is filled automatically from the task\'s dependencies.')
    try:
        tool.input_model.model_validate(task.arguments)
    except ValidationError as exc:
        for err in exc.errors(include_url=False, include_context=False, include_input=False):
            field_name = str(err["loc"][0]) if err["loc"] else ""
            if field_name in tool.bound_inputs and err["type"] == "missing":
                continue  # filled at run time
            where = ".".join(str(p) for p in err["loc"]) or "arguments"
            errors.add(f'Task "{task.id}" ({tool.name}): {where}: {err["msg"]}.')


def _check_shape(draft: PlannerOutput, tools: ToolRegistry, errors: _Errors) -> None:
    """Workflow shape rules: every data step feeds exactly one final summary; side effects come last.

    This keeps how results flow simple and predictable: the summary sees all fetched data, and an
    external action (Telegram) can only send text the summary produced and the user approved.
    """
    by_id = {t.id: t for t in draft.tasks}
    summaries = [t for t in draft.tasks if t.tool == SYNTHESIS_TOOL]
    if len(summaries) != 1:
        errors.add(f'A workflow needs exactly one "{SYNTHESIS_TOOL}" task to write the result (found {len(summaries)}).')
        return
    summary = summaries[0]

    for task in draft.tasks:
        tool = tools.get(task.tool)
        assert tool is not None
        if task.tool == SYNTHESIS_TOOL:
            if not task.depends_on:
                errors.add(f'"{SYNTHESIS_TOOL}" task "{task.id}" must depend on the data tasks it summarizes.')
            continue
        if tool.risk == "external_write":
            if task.depends_on != [summary.id]:
                errors.add(
                    f'Task "{task.id}" ({tool.name}) must depend only on the "{SYNTHESIS_TOOL}" task "{summary.id}", '
                    "whose text it sends."
                )
            continue
        # Data (read) tasks: their results must reach the summary directly.
        if task.id not in summary.depends_on:
            errors.add(f'"{SYNTHESIS_TOOL}" task "{summary.id}" must depend on data task "{task.id}" so its result is used.')
        for dep in task.depends_on:
            if by_id[dep].tool == SYNTHESIS_TOOL:
                errors.add(f'Data task "{task.id}" cannot depend on the "{SYNTHESIS_TOOL}" task.')


def _to_workflow_task(task, tools: ToolRegistry) -> WorkflowTask:  # type: ignore[no-untyped-def]
    tool = tools.get(task.tool)
    assert tool is not None
    return WorkflowTask(
        id=task.id,
        title=task.title.strip()[:80],
        tool_name=task.tool,
        arguments=task.arguments,
        depends_on=list(task.depends_on),
        requires_approval=tool.risk == "external_write",  # from the tool definition, never the LLM
    )
