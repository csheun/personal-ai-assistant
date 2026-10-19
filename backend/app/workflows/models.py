"""Workflow API contract. Mirrors `frontend/src/lib/api/types.ts` field for field.

Conventions:
- snake_case JSON; IDs are opaque strings; timestamps are ISO-8601 UTC; durations are ms.
- Every state change is a `WorkflowEvent`. A run snapshot is the result of applying its
  events in order (see `reducer.py`), and `last_event_id` says which event it reflects.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.client import LLMUsage
from app.tools import ToolResult

ToolName = Literal[
    "get_weather",
    "calendar_list_events",
    "gmail_search",
    "web_search",
    "document_search",
    "summarize",
    "telegram_send_message",
]

TaskStatus = Literal["pending", "running", "waiting_for_approval", "completed", "failed", "skipped", "cancelled"]
RunStatus = Literal["planned", "running", "waiting_for_approval", "completed", "failed", "cancelled"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]
ApprovalDecision = Literal["approve", "reject"]

TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"completed", "failed", "skipped", "cancelled"})
TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Planning metadata -------------------------------------------------------------


class PlanningInfo(Model):
    """How a reply or plan was produced: by which planner, in how many LLM attempts, at what cost."""

    planner: Literal["mock", "llm"]
    attempts: int
    duration_ms: int
    usage: list[LLMUsage] = Field(default_factory=list)


# --- Conversations ---------------------------------------------------------------


class Conversation(Model):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    preview: str


class ChatMessage(Model):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    run_id: str | None = None
    # Set on assistant messages: how the reply (or the plan it introduces) was produced.
    planning: PlanningInfo | None = None


# --- Workflows -------------------------------------------------------------------


class ApprovalPreview(Model):
    destination: str
    body: str


class ApprovalRequest(Model):
    id: str
    run_id: str
    task_id: str
    tool_name: ToolName
    action: str
    preview: ApprovalPreview
    status: ApprovalStatus
    created_at: datetime
    resolved_at: datetime | None = None


class WorkflowTask(Model):
    id: str
    title: str
    tool_name: ToolName
    arguments: dict[str, Any]
    depends_on: list[str]
    requires_approval: bool
    status: TaskStatus = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    result: ToolResult | None = None
    status_reason: str | None = None


class WorkflowRun(Model):
    id: str
    conversation_id: str
    goal: str
    status: RunStatus = "planned"
    tasks: list[WorkflowTask]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: str | None = None
    approvals: list[ApprovalRequest] = Field(default_factory=list)
    last_event_id: int = 0
    planning: PlanningInfo | None = None


# --- Events: one envelope, typed `data` per event type ------------------------------


class _Event(Model):
    id: int = Field(description="Monotonic per run, starting at 1. Sent as the SSE `id:`.")
    run_id: str
    timestamp: datetime
    task_id: str | None = None


class Empty(Model):
    pass


class TaskCompletedData(Model):
    result: ToolResult
    duration_ms: int


class TaskFailedData(Model):
    result: ToolResult
    duration_ms: int
    reason: str


class ReasonData(Model):
    reason: str


class ApprovalData(Model):
    approval: ApprovalRequest


class SummaryData(Model):
    summary: str


class RunStarted(_Event):
    type: Literal["run.started"] = "run.started"
    data: Empty = Field(default_factory=Empty)


class TaskStarted(_Event):
    type: Literal["task.started"] = "task.started"
    data: Empty = Field(default_factory=Empty)


class TaskCompleted(_Event):
    type: Literal["task.completed"] = "task.completed"
    data: TaskCompletedData


class TaskFailed(_Event):
    type: Literal["task.failed"] = "task.failed"
    data: TaskFailedData


class TaskSkipped(_Event):
    type: Literal["task.skipped"] = "task.skipped"
    data: ReasonData


class TaskCancelled(_Event):
    type: Literal["task.cancelled"] = "task.cancelled"
    data: Empty = Field(default_factory=Empty)


class ApprovalRequested(_Event):
    type: Literal["approval.requested"] = "approval.requested"
    data: ApprovalData


class ApprovalResolved(_Event):
    type: Literal["approval.resolved"] = "approval.resolved"
    data: ApprovalData


class RunCompleted(_Event):
    type: Literal["run.completed"] = "run.completed"
    data: SummaryData


class RunFailed(_Event):
    type: Literal["run.failed"] = "run.failed"
    data: ReasonData


class RunCancelled(_Event):
    type: Literal["run.cancelled"] = "run.cancelled"
    data: Empty = Field(default_factory=Empty)


WorkflowEvent = Annotated[
    RunStarted
    | TaskStarted
    | TaskCompleted
    | TaskFailed
    | TaskSkipped
    | TaskCancelled
    | ApprovalRequested
    | ApprovalResolved
    | RunCompleted
    | RunFailed
    | RunCancelled,
    Field(discriminator="type"),
]

RUN_ENDING_EVENTS: frozenset[str] = frozenset({"run.completed", "run.failed", "run.cancelled"})


# --- Request / response payloads ---------------------------------------------------------


class SendMessageRequest(Model):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)


class SendMessageResponse(Model):
    conversation: Conversation
    user_message: ChatMessage
    assistant_message: ChatMessage
    run: WorkflowRun | None


class ApprovalDecisionRequest(Model):
    approval_id: str
    decision: ApprovalDecision


class ToolInfo(Model):
    name: str
    description: str
    risk: Literal["read", "external_write"]
    mocked: bool


class Capabilities(Model):
    """GET /api/capabilities: what this backend can do right now (no secrets)."""

    mode: Literal["mock", "live"]
    llm_model: str | None
    tools: list[ToolInfo]


class UsageStats(Model):
    total_runs: int
    completed_runs: int
    failed_runs: int
    cancelled_runs: int
    tool_calls: int
    approvals_requested: int
    approvals_approved: int
    time_saved_by_parallelism_ms: int
    # LLM usage across planning and summaries (0 in mock mode).
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
