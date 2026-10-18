import type {
  ApprovalDecision,
  ApprovalRequest,
  ChatMessage,
  Conversation,
  ID,
  SendMessageRequest,
  SendMessageResponse,
  UsageStats,
  WorkflowEvent,
  WorkflowRun,
} from "./types";

/**
 * Everything the UI is allowed to ask of the backend.
 *
 * The mock implementation lives in `./mock`. A future `HttpApiClient` will
 * implement the same interface with `fetch` + `EventSource`; components and
 * hooks will not change. Each method documents the FastAPI route it maps to.
 */
export interface ApiClient {
  /** GET /api/conversations */
  listConversations(): Promise<Conversation[]>;

  /** GET /api/conversations/{id}/messages */
  listMessages(conversationId: ID): Promise<ChatMessage[]>;

  /** POST /api/chat */
  sendMessage(request: SendMessageRequest): Promise<SendMessageResponse>;

  /** GET /api/runs/{id} */
  getRun(runId: ID): Promise<WorkflowRun>;

  /** POST /api/runs/{id}/start — begin executing a planned run. */
  startRun(runId: ID): Promise<WorkflowRun>;

  /** POST /api/runs/{id}/cancel */
  cancelRun(runId: ID): Promise<WorkflowRun>;

  /** POST /api/approvals/{id} with body {"decision": "approve" | "reject"} */
  resolveApproval(approvalId: ID, decision: ApprovalDecision): Promise<ApprovalRequest>;

  /** GET /api/stats */
  getStats(): Promise<UsageStats>;

  /**
   * GET /api/runs/{id}/events (Server-Sent Events).
   *
   * Calls `onEvent` for each event in order. Events after `afterSeq` that were
   * already emitted are replayed first (SSE `Last-Event-ID`), so subscribing
   * after loading a snapshot misses nothing and repeats nothing.
   * Returns an unsubscribe function (the equivalent of `EventSource.close()`).
   */
  subscribeToRun(runId: ID, onEvent: (event: WorkflowEvent) => void, afterSeq?: number): () => void;
}
