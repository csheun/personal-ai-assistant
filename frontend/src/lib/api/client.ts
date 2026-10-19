import type {
  ApprovalDecision,
  ApprovalRequest,
  Capabilities,
  ChatMessage,
  Conversation,
  ID,
  SendMessageRequest,
  SendMessageResponse,
  UsageStats,
  WorkflowEvent,
  WorkflowRun,
} from "./types";

/** Whether the backend is reachable. "checking" until the first answer. */
export type ConnectionStatus = "checking" | "online" | "offline";

/** State of a live event stream, for showing "Reconnecting…" in the UI. */
export type StreamStatus = "connecting" | "live" | "reconnecting" | "closed";

export interface RunStreamHandlers {
  onEvent(event: WorkflowEvent): void;
  onStatusChange?(status: StreamStatus): void;
}

/**
 * Everything the UI may ask of the backend. Two implementations:
 * - `HttpWorkflowClient`: FastAPI over fetch + Server-Sent Events.
 * - `MockWorkflowClient`: the same behavior in the browser, for demos without a backend.
 * `createWorkflowClient()` picks one from NEXT_PUBLIC_API_MODE. Components and hooks
 * never know which one they're using.
 */
export interface WorkflowClient {
  /** GET /api/conversations */
  listConversations(): Promise<Conversation[]>;

  /** GET /api/conversations/{id}/messages */
  listMessages(conversationId: ID): Promise<ChatMessage[]>;

  /** POST /api/chat. A proposed workflow comes back as a run in status "planned". */
  sendMessage(request: SendMessageRequest): Promise<SendMessageResponse>;

  /** GET /api/workflows/{id}: snapshot, including `last_event_id`. */
  getRun(runId: ID): Promise<WorkflowRun>;

  /** POST /api/workflows/{id}/start */
  startRun(runId: ID): Promise<WorkflowRun>;

  /** POST /api/workflows/{id}/cancel */
  cancelRun(runId: ID): Promise<WorkflowRun>;

  /** POST /api/workflows/{id}/approve with {"approval_id", "decision": "approve" | "reject"} */
  resolveApproval(runId: ID, approvalId: ID, decision: ApprovalDecision): Promise<ApprovalRequest>;

  /** GET /api/stats */
  getStats(): Promise<UsageStats>;

  /** GET /api/capabilities: mode, model and available tools. */
  getCapabilities(): Promise<Capabilities>;

  /**
   * GET /api/workflows/{id}/events (SSE). Delivers events with id > `afterId` in order,
   * then live ones, reconnecting transparently. Returns a function that closes the stream.
   */
  subscribeToRun(runId: ID, handlers: RunStreamHandlers, afterId?: number): () => void;

  /**
   * Reports backend reachability now and whenever it changes (GET /health while watched,
   * plus the outcome of every request). Returns a function that stops watching.
   */
  watchConnection(listener: (status: ConnectionStatus) => void): () => void;
}
