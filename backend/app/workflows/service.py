"""WorkflowService: the only object the HTTP routes talk to.

Owns the in-memory store (conversations, messages, runs) and every run's WorkflowRunner.
Runs execute in background asyncio tasks owned here, not by any request, so a client
disconnecting from the event stream never affects execution.

Milestone 4+: swap the dicts for a repository backed by PostgreSQL; the API stays the same.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import datetime

from app.llm.client import LLMUsage
from app.tools import ToolRegistry
from app.workflows.errors import NotFound
from app.workflows.graph import parallel_saving_ms
from app.workflows.models import (
    Capabilities,
    ToolInfo,
    ApprovalDecision,
    ApprovalRequest,
    ChatMessage,
    Conversation,
    SendMessageRequest,
    SendMessageResponse,
    UsageStats,
    WorkflowEvent,
    WorkflowRun,
)
from app.workflows.plans import Plan, Planner
from app.workflows.runner import WorkflowRunner, utc_now


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class WorkflowService:
    def __init__(
        self,
        tools: ToolRegistry,
        planner: Planner,
        *,
        clock: Callable[[], datetime] = utc_now,
        mode: str = "mock",
        llm_model: str | None = None,
    ) -> None:
        self._tools = tools
        self._planner = planner
        self._clock = clock
        self._mode = mode
        self._llm_model = llm_model
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[ChatMessage]] = {}
        self._runners: dict[str, WorkflowRunner] = {}

    # --- conversations ------------------------------------------------------------

    def list_conversations(self) -> list[Conversation]:
        return sorted(self._conversations.values(), key=lambda c: c.updated_at, reverse=True)

    def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        if conversation_id not in self._messages:
            raise NotFound("Conversation not found.")
        return list(self._messages[conversation_id])

    async def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        """Plans a reply. A plan becomes a run in status "planned"; nothing executes until start().

        May raise AssistantUnavailable / LLMUnavailable (503) or PlanningFailed (502). Nothing is
        stored unless planning succeeds.
        """
        if request.conversation_id and request.conversation_id not in self._conversations:
            raise NotFound("Conversation not found.")

        # "Today" in the server's time zone, for resolving "tomorrow" etc.
        outcome = await self._planner.plan(request.message, today=self._clock().astimezone().date())
        now = self._clock()

        if request.conversation_id:
            conversation = self._conversations[request.conversation_id].model_copy(
                update={"updated_at": now, "preview": _first_line(request.message)}
            )
        else:
            conversation = Conversation(
                id=new_id("conv"),
                title=_title(request.message),
                created_at=now,
                updated_at=now,
                preview=_first_line(request.message),
            )

        run = None
        if isinstance(outcome, Plan):
            run = WorkflowRun(
                id=new_id("run"),
                conversation_id=conversation.id,
                goal=outcome.goal,
                tasks=outcome.tasks,
                created_at=now,
                planning=outcome.planning,
            )
            self._runners[run.id] = WorkflowRunner(
                run, self._tools, fail_task_ids=outcome.fail_task_ids, clock=self._clock, new_id=new_id
            )

        user_message = ChatMessage(
            id=new_id("msg"), conversation_id=conversation.id, role="user", content=request.message, created_at=now
        )
        assistant_message = ChatMessage(
            id=new_id("msg"),
            conversation_id=conversation.id,
            role="assistant",
            content=outcome.reply,
            created_at=now,
            run_id=run.id if run else None,
            planning=outcome.planning,
        )
        self._conversations[conversation.id] = conversation
        self._messages.setdefault(conversation.id, []).extend([user_message, assistant_message])
        return SendMessageResponse(
            conversation=conversation, user_message=user_message, assistant_message=assistant_message, run=run
        )

    # --- workflows ------------------------------------------------------------------

    def get_run(self, run_id: str) -> WorkflowRun:
        return self._runner(run_id).run

    def start(self, run_id: str) -> WorkflowRun:
        runner = self._runner(run_id)
        runner.start()
        return runner.run

    def cancel(self, run_id: str) -> WorkflowRun:
        runner = self._runner(run_id)
        runner.cancel()
        return runner.run

    def resolve_approval(self, run_id: str, approval_id: str, decision: ApprovalDecision) -> ApprovalRequest:
        return self._runner(run_id).resolve_approval(approval_id, decision)

    def follow(
        self, run_id: str, after_id: int = 0, heartbeat_seconds: float | None = None
    ) -> AsyncIterator[WorkflowEvent | None]:
        """Events after `after_id`, then live ones until the run ends (None = heartbeat)."""
        return self._runner(run_id).log.follow(after_id, heartbeat_seconds)

    def stats(self) -> UsageStats:
        runs = [r.run for r in self._runners.values() if r.run.started_at]
        approvals = [a for r in runs for a in r.approvals]
        return UsageStats(
            total_runs=len(runs),
            completed_runs=sum(r.status == "completed" for r in runs),
            failed_runs=sum(r.status == "failed" for r in runs),
            cancelled_runs=sum(r.status == "cancelled" for r in runs),
            tool_calls=sum(t.started_at is not None for r in runs for t in r.tasks),
            approvals_requested=len(approvals),
            approvals_approved=sum(a.status == "approved" for a in approvals),
            time_saved_by_parallelism_ms=sum(parallel_saving_ms(r.tasks) for r in runs if r.finished_at),
            **self._llm_totals(),
        )

    def _llm_totals(self) -> dict[str, int]:
        """Every recorded LLM call: planning (on assistant messages) and summaries (in task results)."""
        usages = [u for msgs in self._messages.values() for m in msgs if m.planning for u in m.planning.usage]
        for runner in self._runners.values():
            for task in runner.run.tasks:
                usage = ((task.result.output or {}) if task.result else {}).get("usage")
                if isinstance(usage, dict):
                    usages.append(LLMUsage.model_validate(usage))
        return {
            "llm_calls": len(usages),
            "llm_input_tokens": sum(u.input_tokens or 0 for u in usages),
            "llm_output_tokens": sum(u.output_tokens or 0 for u in usages),
        }

    def capabilities(self) -> Capabilities:
        tools = [self._tools.get(name) for name in self._tools.names]
        return Capabilities(
            mode=self._mode,  # type: ignore[arg-type]
            llm_model=self._llm_model,
            tools=[ToolInfo(name=t.name, description=t.description, risk=t.risk, mocked=t.mocked) for t in tools if t],
        )

    async def shutdown(self) -> None:
        """Cancel unfinished runs so no background tasks outlive the app."""
        for runner in self._runners.values():
            if runner.run.status not in {"completed", "failed", "cancelled"}:
                runner.cancel()

    def _runner(self, run_id: str) -> WorkflowRunner:
        runner = self._runners.get(run_id)
        if runner is None:
            raise NotFound("Workflow run not found.")
        return runner


def _first_line(text: str) -> str:
    return text.strip().split("\n")[0]


def _title(text: str) -> str:
    line = _first_line(text)
    if len(line) <= 56:
        return line
    cut = line[:54]
    return f"{cut[: cut.rfind(' ')].rstrip()}…"
