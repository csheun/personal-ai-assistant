/**
 * WorkflowClient backed by the FastAPI server: REST over fetch, live events over SSE.
 * All workflow execution happens on the server; this class only moves data.
 */
import type { ConnectionStatus, RunStreamHandlers, StreamStatus, WorkflowClient } from "./client";
import {
  ApiError,
  type ApprovalDecision,
  type ApprovalRequest,
  type ChatMessage,
  type Conversation,
  type ID,
  type SendMessageRequest,
  type SendMessageResponse,
  type UsageStats,
  type WorkflowEvent,
  type WorkflowRun,
} from "./types";

const RUN_ENDING = new Set(["run.completed", "run.failed", "run.cancelled"]);
/** Health-check interval: quick while the backend is down, relaxed while it's up. */
const HEALTH_CHECK_MS = { online: 5_000, offline: 3_000, checking: 3_000 } as const;
const FINISHED = new Set(["completed", "failed", "cancelled"]);

type EventSourceFactory = (url: string) => EventSource;

export interface HttpClientOptions {
  /** Injected in tests. */
  fetch?: typeof fetch;
  eventSource?: EventSourceFactory;
}

export class HttpWorkflowClient implements WorkflowClient {
  private readonly fetch: typeof fetch;
  private readonly openEventSource: EventSourceFactory;
  private connection: ConnectionStatus = "checking";
  private readonly connectionListeners = new Set<(status: ConnectionStatus) => void>();
  private healthTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(
    private readonly baseUrl: string,
    options: HttpClientOptions = {},
  ) {
    this.fetch = options.fetch ?? ((...args) => globalThis.fetch(...args));
    this.openEventSource = options.eventSource ?? ((url) => new EventSource(url));
  }

  listConversations(): Promise<Conversation[]> {
    return this.request("/api/conversations");
  }

  listMessages(conversationId: ID): Promise<ChatMessage[]> {
    return this.request(`/api/conversations/${encodeURIComponent(conversationId)}/messages`);
  }

  sendMessage(request: SendMessageRequest): Promise<SendMessageResponse> {
    return this.request("/api/chat", { method: "POST", body: request });
  }

  getRun(runId: ID): Promise<WorkflowRun> {
    return this.request(`/api/workflows/${encodeURIComponent(runId)}`);
  }

  startRun(runId: ID): Promise<WorkflowRun> {
    return this.request(`/api/workflows/${encodeURIComponent(runId)}/start`, { method: "POST" });
  }

  cancelRun(runId: ID): Promise<WorkflowRun> {
    return this.request(`/api/workflows/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
  }

  resolveApproval(runId: ID, approvalId: ID, decision: ApprovalDecision): Promise<ApprovalRequest> {
    return this.request(`/api/workflows/${encodeURIComponent(runId)}/approve`, {
      method: "POST",
      body: { approval_id: approvalId, decision },
    });
  }

  getStats(): Promise<UsageStats> {
    return this.request("/api/stats");
  }

  /**
   * Opens an SSE stream. The browser reconnects by itself after network blips and sends
   * `Last-Event-ID`, so the server resumes where we left off; duplicates are dropped here
   * by event id. The stream is closed when the run ends or the caller unsubscribes.
   */
  subscribeToRun(runId: ID, handlers: RunStreamHandlers, afterId = 0): () => void {
    let lastId = afterId;
    let closed = false;
    const setStatus = (status: StreamStatus) => handlers.onStatusChange?.(status);

    const url = `${this.baseUrl}/api/workflows/${encodeURIComponent(runId)}/events?after=${afterId}`;
    const source = this.openEventSource(url);
    setStatus("connecting");

    const close = () => {
      if (closed) return;
      closed = true;
      source.close();
      setStatus("closed");
    };

    source.onopen = () => setStatus("live");

    source.onmessage = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as WorkflowEvent;
      if (event.id <= lastId) return; // already applied (replay after reconnect)
      lastId = event.id;
      handlers.onEvent(event);
      if (RUN_ENDING.has(event.type)) close();
    };

    source.onerror = () => {
      if (closed) return;
      setStatus("reconnecting");
      // The server also ends the stream normally once a run is over. If the run is finished
      // and we've seen every event, stop instead of letting EventSource reconnect forever.
      this.getRun(runId).then(
        (run) => {
          if (FINISHED.has(run.status) && run.last_event_id <= lastId) close();
        },
        () => {}, // server unreachable: keep retrying
      );
    };

    return close;
  }

  watchConnection(listener: (status: ConnectionStatus) => void): () => void {
    this.connectionListeners.add(listener);
    listener(this.connection);
    if (this.connectionListeners.size === 1) void this.checkHealth();
    return () => {
      this.connectionListeners.delete(listener);
      if (this.connectionListeners.size === 0) clearTimeout(this.healthTimer);
    };
  }

  /** Pings GET /health, then schedules the next ping while anyone is watching. */
  private async checkHealth(): Promise<void> {
    clearTimeout(this.healthTimer);
    await this.request("/health").catch(() => {}); // request() records the outcome
    if (this.connectionListeners.size > 0) {
      this.healthTimer = setTimeout(() => void this.checkHealth(), HEALTH_CHECK_MS[this.connection]);
    }
  }

  private setConnection(status: ConnectionStatus): void {
    if (status === this.connection) return;
    this.connection = status;
    this.connectionListeners.forEach((listener) => listener(status));
    // Just went down: replace any relaxed "online" schedule with a quick retry.
    if (status === "offline" && this.connectionListeners.size > 0) {
      clearTimeout(this.healthTimer);
      this.healthTimer = setTimeout(() => void this.checkHealth(), HEALTH_CHECK_MS.offline);
    }
  }

  private async request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
    let response: Response;
    try {
      response = await this.fetch(`${this.baseUrl}${path}`, {
        method: init.method ?? "GET",
        headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}) },
        body: init.body ? JSON.stringify(init.body) : undefined,
      });
    } catch {
      this.setConnection("offline");
      throw new ApiError(0, "Can't reach the assistant server. Check that the backend is running and try again.");
    }
    // Any HTTP response, even an error status, means the server is reachable.
    this.setConnection("online");
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
      throw new ApiError(response.status, describeDetail(body?.detail) ?? `The server returned an error (${response.status}).`);
    }
    return (await response.json()) as T;
  }
}

/** FastAPI errors are `{"detail": "text"}` or, for validation, `{"detail": [{"msg": ...}, ...]}`. */
function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : null)).filter(Boolean);
    return messages.length ? messages.join(" ") : null;
  }
  return null;
}
