/**
 * Demo-mode WorkflowClient: the whole backend simulated in the browser.
 * Behaves like FastAPI (latency, validation errors, 404/409s, event streams)
 * with no network calls and no real external actions.
 */
import type { ConnectionStatus, RunStreamHandlers, WorkflowClient } from "@/lib/api/client";
import {
  ApiError,
  type ApprovalDecision,
  type ApprovalRequest,
  type Capabilities,
  type ChatMessage,
  type Conversation,
  type ID,
  type SendMessageRequest,
  type SendMessageResponse,
  type UsageStats,
  type WorkflowRun,
  type WorkflowTask,
} from "@/lib/api/types";
import { realScheduler, WorkflowEngine, type Scheduler } from "./engine";
import { planFromMessage, toWorkflowTask, type Plan } from "./planner";
import { simulateToolResult, TOOL_DURATION_MS } from "./tools";
import { VirtualScheduler } from "./virtual-scheduler";
import { parallelSavingMs } from "@/lib/workflow/metrics";

export interface MockClientOptions {
  scheduler?: Scheduler;
  /** Multiplier on simulated tool durations (0.25 = four times faster). */
  speed?: number;
  /** Simulated network latency per request. */
  latencyMs?: number;
  /** Pre-populate the sidebar with example conversations. */
  seed?: boolean;
}

export const MAX_MESSAGE_LENGTH = 4000;

const MOCK_CAPABILITIES: Capabilities = {
  mode: "mock",
  llm_model: null,
  tools: (
    [
      ["get_weather", "read"],
      ["calendar_list_events", "read"],
      ["gmail_search", "read"],
      ["web_search", "read"],
      ["document_search", "read"],
      ["summarize", "read"],
      ["telegram_send_message", "external_write"],
    ] as const
  ).map(([name, risk]) => ({ name, description: "", risk, mocked: true })),
};

export class MockWorkflowClient implements WorkflowClient {
  private readonly scheduler: Scheduler;
  private readonly speed: number;
  private readonly latencyMs: number;
  private readonly conversations = new Map<ID, Conversation>();
  private readonly messages = new Map<ID, ChatMessage[]>();
  private readonly engines = new Map<ID, WorkflowEngine>();
  private counter = 0;

  constructor(options: MockClientOptions = {}) {
    this.scheduler = options.scheduler ?? realScheduler;
    this.speed = options.speed ?? 1;
    this.latencyMs = options.latencyMs ?? 350;
    if (options.seed) this.seed();
  }

  // --- WorkflowClient ------------------------------------------------------

  listConversations(): Promise<Conversation[]> {
    return this.respond(() => [...this.conversations.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
  }

  listMessages(conversationId: ID): Promise<ChatMessage[]> {
    return this.respond(() => {
      const messages = this.messages.get(conversationId);
      if (!messages) throw new ApiError(404, "Conversation not found.");
      return messages;
    });
  }

  sendMessage(request: SendMessageRequest): Promise<SendMessageResponse> {
    return this.respond(() => {
      const text = request.message.trim();
      if (!text) throw new ApiError(422, "Message can't be empty.");
      if (text.length > MAX_MESSAGE_LENGTH) throw new ApiError(422, `Message is longer than ${MAX_MESSAGE_LENGTH} characters.`);
      if (request.conversation_id && !this.conversations.has(request.conversation_id)) {
        throw new ApiError(404, "Conversation not found.");
      }

      const outcome = planFromMessage(text);
      if (outcome.kind === "error") throw new ApiError(outcome.status, outcome.message);

      return this.recordExchange(request.conversation_id, text, outcome.kind === "plan" ? outcome.plan : outcome.reply);
    });
  }

  getRun(runId: ID): Promise<WorkflowRun> {
    return this.respond(() => this.engine(runId).run);
  }

  startRun(runId: ID): Promise<WorkflowRun> {
    return this.respond(() => {
      const engine = this.engine(runId);
      engine.start();
      return engine.run;
    });
  }

  cancelRun(runId: ID): Promise<WorkflowRun> {
    return this.respond(() => {
      const engine = this.engine(runId);
      engine.cancel();
      return engine.run;
    });
  }

  resolveApproval(runId: ID, approvalId: ID, decision: ApprovalDecision): Promise<ApprovalRequest> {
    return this.respond(() => this.engine(runId).resolveApproval(approvalId, decision));
  }

  getCapabilities(): Promise<Capabilities> {
    return this.respond(() => MOCK_CAPABILITIES);
  }

  getStats(): Promise<UsageStats> {
    return this.respond(() => computeStats([...this.engines.values()].map((e) => e.run)));
  }

  subscribeToRun(runId: ID, handlers: RunStreamHandlers, afterId = 0): () => void {
    handlers.onStatusChange?.("live");
    const unsubscribe = this.engine(runId).subscribe((event) => handlers.onEvent(structuredClone(event)), afterId);
    return () => {
      unsubscribe();
      handlers.onStatusChange?.("closed");
    };
  }

  /** Nothing to connect to in demo mode. */
  watchConnection(listener: (status: ConnectionStatus) => void): () => void {
    listener("online");
    return () => {};
  }

  // --- internals -----------------------------------------------------------

  /** Simulates a network round trip: latency, and a copy of the data (as if JSON-serialized). */
  private respond<T>(handler: () => T): Promise<T> {
    return new Promise((resolve, reject) => {
      this.scheduler.setTimeout(() => {
        try {
          resolve(structuredClone(handler()));
        } catch (error) {
          reject(error);
        }
      }, this.latencyMs);
    });
  }

  private engine(runId: ID): WorkflowEngine {
    const engine = this.engines.get(runId);
    if (!engine) throw new ApiError(404, "Workflow run not found.");
    return engine;
  }

  private newId(prefix: string): ID {
    return `${prefix}_${++this.counter}`;
  }

  private recordExchange(
    conversationId: ID | null,
    text: string,
    answer: Plan | string,
    scheduler: Scheduler = this.scheduler,
  ): SendMessageResponse {
    const now = new Date(scheduler.now()).toISOString();
    const conversation: Conversation = conversationId
      ? { ...this.conversations.get(conversationId)!, updated_at: now }
      : { id: this.newId("conv"), title: titleFrom(text), created_at: now, updated_at: now, preview: "" };

    const plan = typeof answer === "string" ? null : answer;
    const run = plan ? this.createRun(conversation.id, plan, now, scheduler) : null;

    const userMessage: ChatMessage = {
      id: this.newId("msg"),
      conversation_id: conversation.id,
      role: "user",
      content: text,
      created_at: now,
    };
    const assistantMessage: ChatMessage = {
      id: this.newId("msg"),
      conversation_id: conversation.id,
      role: "assistant",
      content: plan ? plan.reply : (answer as string),
      created_at: now,
      ...(run ? { run_id: run.id } : {}),
    };

    conversation.preview = text.split("\n")[0];
    this.conversations.set(conversation.id, conversation);
    this.messages.set(conversation.id, [...(this.messages.get(conversation.id) ?? []), userMessage, assistantMessage]);

    return { conversation, user_message: userMessage, assistant_message: assistantMessage, run };
  }

  private createRun(conversationId: ID, plan: Plan, now: string, scheduler: Scheduler): WorkflowRun {
    const run: WorkflowRun = {
      id: this.newId("run"),
      conversation_id: conversationId,
      goal: plan.goal,
      status: "planned",
      tasks: plan.tasks.map(toWorkflowTask),
      created_at: now,
      started_at: null,
      finished_at: null,
      summary: null,
      approvals: [],
      last_event_id: 0,
    };
    const failures = new Set(plan.failTaskIds);

    const engine = new WorkflowEngine(run, {
      scheduler,
      durationFor: (task) => Math.round(TOOL_DURATION_MS[task.tool_name] * this.speed),
      execute: (task, upstream) => simulateToolResult(task, upstream, failures.has(task.id)),
      approvalFor: (task, current) => ({
        action: `Send a Telegram message to ${String(task.arguments.chat)}`,
        preview: { destination: `Telegram · ${String(task.arguments.chat)}`, body: summaryText(current, task) },
      }),
      summarize: buildFinalSummary,
      newId: (prefix) => this.newId(prefix),
    });
    this.engines.set(run.id, engine);
    return run;
  }

  /** Example history, executed instantly on a virtual clock so it has real timestamps and events. */
  private seed(): void {
    const examples = [
      { at: "2026-10-16T23:40:00.000Z", message: "Give me a morning briefing and send it to Telegram" },
      { at: "2026-10-15T09:12:00.000Z", message: "What's the weather in Tokyo and the latest news on cherry blossom season?" },
      { at: "2026-10-14T14:05:00.000Z", message: "What can you do?" },
    ];
    for (const { at, message } of examples) {
      const clock = new VirtualScheduler(Date.parse(at));
      const outcome = planFromMessage(message);
      if (outcome.kind === "error") continue;
      const { run } = this.recordExchange(null, message, outcome.kind === "plan" ? outcome.plan : outcome.reply, clock);
      if (!run) continue;

      const engine = this.engines.get(run.id)!;
      engine.start();
      clock.runAll();
      for (const approval of engine.run.approvals.filter((a) => a.status === "pending")) {
        engine.resolveApproval(approval.id, "approve");
        clock.runAll();
      }
    }
  }
}

function titleFrom(text: string): string {
  const firstLine = text.split("\n")[0].trim();
  if (firstLine.length <= 56) return firstLine;
  const cut = firstLine.slice(0, 54);
  return `${cut.slice(0, cut.lastIndexOf(" ")).trimEnd()}…`;
}

function summaryText(run: WorkflowRun, task: WorkflowTask): string {
  const source = run.tasks.find((t) => task.depends_on.includes(t.id) && t.tool_name === "summarize");
  return String((source?.result?.output as { text?: string } | null)?.text ?? "");
}

function buildFinalSummary(run: WorkflowRun): string {
  const summarizeTask = run.tasks.find((t) => t.tool_name === "summarize");
  const text = String((summarizeTask?.result?.output as { text?: string } | null)?.text ?? "All steps finished.");
  const telegram = run.tasks.find((t) => t.tool_name === "telegram_send_message");
  if (!telegram) return text;
  if (telegram.status === "completed") return `${text}\n\nYou approved the Telegram message. In mock mode nothing was actually sent.`;
  return `${text}\n\nI didn't send anything to Telegram because you rejected the message.`;
}

export function computeStats(runs: WorkflowRun[]): UsageStats {
  const started = runs.filter((r) => r.started_at);
  const tasks = started.flatMap((r) => r.tasks);
  const approvals = started.flatMap((r) => r.approvals);
  const saved = started.filter((r) => r.finished_at).reduce((total, r) => total + parallelSavingMs(r.tasks), 0);

  return {
    total_runs: started.length,
    completed_runs: started.filter((r) => r.status === "completed").length,
    failed_runs: started.filter((r) => r.status === "failed").length,
    cancelled_runs: started.filter((r) => r.status === "cancelled").length,
    tool_calls: tasks.filter((t) => t.started_at).length,
    approvals_requested: approvals.length,
    approvals_approved: approvals.filter((a) => a.status === "approved").length,
    time_saved_by_parallelism_ms: saved,
    llm_calls: 0,
    llm_input_tokens: 0,
    llm_output_tokens: 0,
  };
}

