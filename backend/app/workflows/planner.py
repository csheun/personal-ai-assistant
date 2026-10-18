"""MOCK planner: keyword rules that turn a message into a fixed-shape plan.

Same rules as the frontend's demo planner, so both modes behave identically.
Milestone 4 replaces this module with an LLM-backed planner that returns the same `Plan`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.tools import ToolRegistry
from app.workflows.errors import AssistantUnavailable
from app.workflows.models import ToolName, WorkflowTask


@dataclass(frozen=True)
class Plan:
    reply: str
    goal: str
    tasks: list[WorkflowTask]
    # Mock-only failure injection, triggered by "simulate failure" in the message.
    fail_task_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class DirectReply:
    reply: str


@dataclass(frozen=True)
class _Rule:
    tool: ToolName
    noun: str
    pattern: re.Pattern[str]
    build: Callable[[str], tuple[str, dict[str, Any]]]


def _weather(message: str) -> tuple[str, dict[str, Any]]:
    match = re.search(r"\bin ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)", message)
    city = match.group(1) if match else "Singapore"
    return f"Check {city} weather", {"city": city}


def _search(message: str) -> tuple[str, dict[str, Any]]:
    match = re.search(r"\b(?:news|search|look up|latest|research)(?: (?:about|on|for))? ([^,.?!]+)", message, re.I)
    topic = match.group(1).strip() if match else ""
    query = topic if len(topic) > 2 else "today's top headlines"
    return f"Search the web for {query}", {"query": query}


_RULES = [
    _Rule("get_weather", "the weather", re.compile(r"\b(weather|rain|temperature|forecast|umbrella|briefing)\b", re.I), _weather),
    _Rule(
        "calendar_list_events",
        "your calendar",
        re.compile(r"\b(calendar|schedule|meetings?|agenda|today|briefing)\b", re.I),
        lambda _: ("Read today's calendar", {"date": "today"}),
    ),
    _Rule(
        "gmail_search",
        "your inbox",
        re.compile(r"\b(e-?mails?|gmail|inbox|briefing)\b", re.I),
        lambda _: ("Scan unread email", {"query": "is:unread newer_than:1d"}),
    ),
    _Rule("web_search", "the web", re.compile(r"\b(news|search|look up|latest|research)\b", re.I), _search),
    _Rule(
        "document_search",
        "your documents",
        re.compile(r"\b(docs?|documents?|notes|files?)\b", re.I),
        lambda _: ("Search your documents", {"query": "goals and deadlines"}),
    ),
]
_SEND = re.compile(r"\b(telegram|send|message me|notify)\b", re.I)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


class MockPlanner:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def plan(self, message: str) -> Plan | DirectReply:
        if re.search(r"simulate error", message, re.I):
            # Mock-only: lets you exercise the client's error handling.
            raise AssistantUnavailable("The assistant is unavailable right now. Try again in a moment.")

        rules = [r for r in _RULES if r.pattern.search(message)]
        if not rules:
            return DirectReply(
                "I can check your weather, calendar, email, the web and your documents, and send the result to "
                'Telegram. Try "Give me a morning briefing and send it to Telegram."'
            )

        tasks = [self._task(f"t{i}", r.tool, *r.build(message), depends_on=[]) for i, r in enumerate(rules, 1)]
        summary_id = f"t{len(tasks) + 1}"
        tasks.append(self._task(summary_id, "summarize", "Write a summary", {}, depends_on=[t.id for t in tasks]))

        wants_send = bool(_SEND.search(message))
        if wants_send:
            tasks.append(
                self._task(
                    f"t{len(tasks) + 1}",
                    "telegram_send_message",
                    "Send the summary to Telegram",
                    {"chat": "Me (Saved Messages)"},
                    depends_on=[summary_id],
                )
            )

        sources = [r.noun for r in rules]
        together = " at the same time" if len(sources) > 1 else ""
        reply = f"Here's my plan. I'll check {_join(sources)}{together}, then summarize what I find"
        reply += (
            ". Before anything goes to Telegram, I'll show you the message and wait for your approval."
            if wants_send
            else "."
        )
        reply += " Review the steps and start the run when you're ready."
        return Plan(
            reply=reply,
            goal=f"Gather {_join(sources)}, summarize{', then send to Telegram' if wants_send else ''}.",
            tasks=tasks,
            fail_task_ids=frozenset({tasks[0].id}) if re.search(r"simulate failure", message, re.I) else frozenset(),
        )

    def _task(
        self, task_id: str, tool: ToolName, title: str, arguments: dict[str, Any], depends_on: list[str]
    ) -> WorkflowTask:
        definition = self._registry.get(tool)
        if definition is None:
            raise ValueError(f"Planner referenced unknown tool {tool}")
        # Approval comes from the tool definition, so no plan can skip it for a side-effecting tool.
        return WorkflowTask(
            id=task_id,
            title=title,
            tool_name=tool,
            arguments=arguments,
            depends_on=depends_on,
            requires_approval=definition.side_effects,
        )
