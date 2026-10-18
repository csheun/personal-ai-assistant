"""Fills in arguments that come from earlier tasks' results.

Plans are fixed before execution, but some inputs only exist at run time: the
summary needs its sources' outputs, and Telegram sends the summary's text.
Milestone 4's LLM planner can express bindings in the plan; the runner API stays the same.
"""

from typing import Any

from app.workflows.models import WorkflowTask


def resolve_arguments(task: WorkflowTask, upstream: list[WorkflowTask]) -> dict[str, Any]:
    outputs = [(t.tool_name, (t.result.output if t.result else None) or {}) for t in upstream]
    match task.tool_name:
        case "summarize":
            return {**task.arguments, "sources": [{"tool_name": name, "output": out} for name, out in outputs]}
        case "telegram_send_message":
            text = next((out.get("text") for name, out in outputs if name == "summarize"), None)
            return {**task.arguments, "text": text or ""}
    return task.arguments
