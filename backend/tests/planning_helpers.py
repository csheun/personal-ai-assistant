from typing import Any

from app.tools import ToolRegistry, build_default_registry

PLANNER_TOOLS = {"get_weather", "web_search", "summarize", "telegram_send_message"}


def planner_tools() -> ToolRegistry:
    return build_default_registry().filtered(lambda t: t.name in PLANNER_TOOLS)


def task(id: str, tool: str, arguments: dict[str, Any] | None = None, depends_on: list[str] | None = None) -> dict[str, Any]:
    return {"id": id, "title": f"Step {id}", "tool": tool, "arguments": arguments or {}, "depends_on": depends_on or []}


def workflow(*tasks: dict[str, Any], reply: str = "On it.", goal: str = "Do the thing.") -> dict[str, Any]:
    return {"mode": "workflow", "reply": reply, "goal": goal, "tasks": list(tasks)}


# "Check tomorrow's weather in Singapore, search for recent AI news, summarize both, send to Telegram."
DEMO_PLAN = workflow(
    task("t1", "get_weather", {"city": "Singapore"}),
    task("t2", "web_search", {"query": "recent AI news", "max_results": 5}),
    task("t3", "summarize", {"instruction": "Summarize both in 3 sentences."}, ["t1", "t2"]),
    task("t4", "telegram_send_message", {}, ["t3"]),
)
