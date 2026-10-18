/**
 * API contracts shared by the mock client and the future FastAPI client.
 *
 * Field names are snake_case on purpose: they are the exact JSON shapes the
 * FastAPI/Pydantic backend will send, so no mapping layer is needed.
 * Timestamps are ISO-8601 strings; durations are milliseconds.
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

export interface ToolResult {
  tool_name: ToolName;
  ok: boolean;
  /** Validated tool output; shape depends on the tool. */
  output: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
  /** True when the data is simulated. Always true in mock mode. */
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
  /** Seq of the last event reflected in this snapshot. Resume the stream after it. */
  last_event_seq: number;
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
// Events (the SSE stream: GET /api/runs/{id}/events)
// ---------------------------------------------------------------------------

interface EventBase {
  run_id: ID;
  /** Monotonic per run; lets the client drop duplicates and detect gaps on reconnect. */
  seq: number;
  timestamp: ISODateTime;
}

export type WorkflowEvent =
  | (EventBase & { type: "run.started" })
  | (EventBase & { type: "task.started"; task_id: ID })
  | (EventBase & { type: "task.completed"; task_id: ID; result: ToolResult; duration_ms: number })
  | (EventBase & { type: "task.failed"; task_id: ID; result: ToolResult; duration_ms: number; reason: string })
  | (EventBase & { type: "task.skipped"; task_id: ID; reason: string })
  | (EventBase & { type: "task.cancelled"; task_id: ID })
  | (EventBase & { type: "approval.requested"; task_id: ID; approval: ApprovalRequest })
  | (EventBase & { type: "approval.resolved"; task_id: ID; approval: ApprovalRequest })
  | (EventBase & { type: "run.completed"; summary: string })
  | (EventBase & { type: "run.failed"; reason: string })
  | (EventBase & { type: "run.cancelled" });

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

/** Error body shape returned by FastAPI (`{"detail": ...}`). */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
