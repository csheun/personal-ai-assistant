/**
 * API contract shared by the mock client and the FastAPI backend.
 *
 * Mirrors `backend/app/workflows/models.py` field for field. Names are snake_case
 * because they are the exact JSON FastAPI sends, so no mapping layer is needed.
 * Timestamps are ISO-8601 UTC strings; durations are milliseconds.
 * `contracts/workflow-scenarios.json` (recorded from the Python runner) is replayed
 * through the TypeScript reducer in tests/unit/contract.test.ts to keep both sides in sync.
 */

export type ID = string;
export type ISODateTime = string;

// ---------------------------------------------------------------------------
// Conversations & messages
// ---------------------------------------------------------------------------

export interface Conversation {
  id: ID;
  title: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  /** First line of the latest message, for the sidebar. */
  preview: string;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: ID;
  conversation_id: ID;
  role: MessageRole;
  content: string;
  created_at: ISODateTime;
  /** Set on assistant messages that proposed a workflow. */
  run_id?: ID;
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

export type ToolName =
  | "get_weather"
  | "calendar_list_events"
  | "gmail_search"
  | "web_search"
  | "document_search"
  | "summarize"
  | "telegram_send_message";

export type ToolErrorCode = "unknown_tool" | "invalid_arguments" | "execution_failed" | "timeout" | "simulated_failure";

export interface ToolError {
  code: ToolErrorCode;
  message: string;
  /** Validation errors, for `invalid_arguments`. */
  details?: Record<string, unknown>[] | null;
}

export interface ToolResult {
  tool_name: ToolName;
  /** The validated arguments the tool actually ran with. */
  arguments: Record<string, unknown>;
  ok: boolean;
  /** Validated tool output; shape depends on the tool. */
  output: Record<string, unknown> | null;
  error: ToolError | null;
  /** True when the data is simulated. Always true until Milestone 4. */
  mocked: boolean;
}

// ---------------------------------------------------------------------------
// Workflows
// ---------------------------------------------------------------------------

export type TaskStatus =
  | "pending" // waiting for dependencies
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed"
  | "skipped" // a dependency failed, or the user rejected the action
  | "cancelled";

export type RunStatus =
  | "planned" // plan proposed, not started yet
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed"
  | "cancelled";

export interface WorkflowTask {
  id: ID;
  /** Short human label, e.g. "Check Singapore weather". */
  title: string;
  tool_name: ToolName;
  arguments: Record<string, unknown>;
  /** IDs of tasks that must complete before this one starts. */
  depends_on: ID[];
  /** External side effects (e.g. sending a message) require explicit approval. */
  requires_approval: boolean;
  status: TaskStatus;
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  /** Wall-clock duration once finished. */
  duration_ms: number | null;
  result: ToolResult | null;
  /** Why the task was skipped/failed, in user-facing language. */
  status_reason: string | null;
}

export interface WorkflowRun {
  id: ID;
  conversation_id: ID;
  /** One-sentence description of the plan, written by the assistant. */
  goal: string;
  status: RunStatus;
  tasks: WorkflowTask[];
  created_at: ISODateTime;
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  /** Final AI summary, set when the run completes. */
  summary: string | null;
  /** Approval requests raised during this run (pending and resolved). */
  approvals: ApprovalRequest[];
  /** Id of the last event reflected in this snapshot. Resume the event stream after it. */
  last_event_id: number;
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired";

export interface ApprovalRequest {
  id: ID;
  run_id: ID;
  task_id: ID;
  tool_name: ToolName;
  /** What will happen, in plain language. */
  action: string;
  /** Exactly what will be sent, so the user approves real content. */
  preview: { destination: string; body: string };
  status: ApprovalStatus;
  created_at: ISODateTime;
  resolved_at: ISODateTime | null;
}

export type ApprovalDecision = "approve" | "reject";

// ---------------------------------------------------------------------------
// Events: GET /api/workflows/{id}/events (SSE). One envelope, typed `data` per type.
// ---------------------------------------------------------------------------

type Empty = Record<string, never>;

interface Envelope<Type extends string, Data> {
  /** Monotonic per run, starting at 1. Also the SSE `id`, so reconnects resume after it. */
  id: number;
  run_id: ID;
  timestamp: ISODateTime;
  /** The task this event is about, or null for run-level events. */
  task_id: ID | null;
  type: Type;
  data: Data;
}

export type WorkflowEvent =
  | Envelope<"run.started", Empty>
  | Envelope<"task.started", Empty>
  | Envelope<"task.completed", { result: ToolResult; duration_ms: number }>
  | Envelope<"task.failed", { result: ToolResult; duration_ms: number; reason: string }>
  | Envelope<"task.skipped", { reason: string }>
  | Envelope<"task.cancelled", Empty>
  | Envelope<"approval.requested", { approval: ApprovalRequest }>
  | Envelope<"approval.resolved", { approval: ApprovalRequest }>
  | Envelope<"run.completed", { summary: string }>
  | Envelope<"run.failed", { reason: string }>
  | Envelope<"run.cancelled", Empty>;

export type WorkflowEventType = WorkflowEvent["type"];

// ---------------------------------------------------------------------------
// Endpoint payloads
// ---------------------------------------------------------------------------

/** POST /api/chat */
export interface SendMessageRequest {
  conversation_id: ID | null;
  message: string;
}

export interface SendMessageResponse {
  conversation: Conversation;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  /** Present when the assistant proposed a workflow; starts in status "planned". */
  run: WorkflowRun | null;
}

/** GET /api/stats */
export interface UsageStats {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  cancelled_runs: number;
  tool_calls: number;
  approvals_requested: number;
  approvals_approved: number;
  /** Sum of task durations minus wall-clock time: what parallel execution saved. */
  time_saved_by_parallelism_ms: number;
}

/**
 * A failed request. `status` is the HTTP status (FastAPI's `{"detail": ...}` becomes the
 * message), or 0 when the server couldn't be reached at all.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
