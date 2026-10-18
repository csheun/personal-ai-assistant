/**
 * MOCK workflow engine: runs a WorkflowRun's task graph in the browser and emits
 * the same events the FastAPI backend will later stream over SSE.
 *
 * Rules it implements (the real backend must follow the same ones):
 * - A task starts as soon as all of its dependencies have completed, so
 *   independent tasks run concurrently.
 * - If a dependency fails, is skipped or is cancelled, dependants are skipped.
 * - Tasks with `requires_approval` pause in `waiting_for_approval` until the
 *   user approves (task runs) or rejects (task is skipped).
 * - Cancelling stops running tasks, expires open approvals and cancels the rest.
 *
 * All state changes go through `applyEvent`, so the engine's view of the run is
 * exactly what a client replaying the event stream would see.
 */
import {
  ApiError,
  type ApprovalDecision,
  type ApprovalRequest,
  type ID,
  type ToolResult,
  type WorkflowEvent,
  type WorkflowRun,
  type WorkflowTask,
} from "@/lib/api/types";
import { blockedTasks, readyTasks, validateDag, isTerminal } from "@/lib/workflow/graph";
import { applyEvent } from "@/lib/workflow/reducer";

/** Injected so tests can control time with fake timers. */
export interface Scheduler {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export const realScheduler: Scheduler = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
};

export interface EngineOptions {
  scheduler: Scheduler;
  /** How long a task takes. */
  durationFor(task: WorkflowTask): number;
  /** Produce the task's (mocked) result. `upstream` are its completed dependencies. */
  execute(task: WorkflowTask, upstream: WorkflowTask[]): ToolResult;
  /** Build what the user is asked to approve. */
  approvalFor(task: WorkflowTask, run: WorkflowRun): Pick<ApprovalRequest, "action" | "preview">;
  /** Final AI summary shown when the run completes. */
  summarize(run: WorkflowRun): string;
  newId(prefix: string): ID;
}

/** What a caller supplies to `emit`; the engine fills in id, run_id and timestamp. */
type EventBody = WorkflowEvent extends infer E
  ? E extends WorkflowEvent
    ? Pick<E, "type" | "data"> & { task_id?: ID }
    : never
  : never;
type Listener = (event: WorkflowEvent) => void;

export class WorkflowEngine {
  private state: WorkflowRun;
  private readonly history: WorkflowEvent[] = [];
  private readonly listeners = new Set<Listener>();
  private readonly timers = new Map<ID, unknown>();

  constructor(
    run: WorkflowRun,
    private readonly options: EngineOptions,
  ) {
    validateDag(run.tasks);
    this.state = run;
  }

  get run(): WorkflowRun {
    return this.state;
  }

  get events(): readonly WorkflowEvent[] {
    return this.history;
  }

  /** Replays events after `afterId` (like SSE Last-Event-ID), then streams live ones. */
  subscribe(listener: Listener, afterId = 0): () => void {
    this.history.filter((e) => e.id > afterId).forEach(listener);
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  start(): void {
    if (this.state.status !== "planned") throw new ApiError(409, "This run has already started.");
    this.emit({ type: "run.started", data: {} });
    this.advance();
  }

  cancel(): void {
    const { status } = this.state;
    if (status === "completed" || status === "failed" || status === "cancelled") {
      throw new ApiError(409, "This run has already finished.");
    }
    for (const [taskId, timer] of this.timers) {
      this.options.scheduler.clearTimeout(timer);
      this.timers.delete(taskId);
    }
    for (const approval of this.state.approvals.filter((a) => a.status === "pending")) {
      this.emit({
        type: "approval.resolved",
        task_id: approval.task_id,
        data: { approval: { ...approval, status: "expired", resolved_at: this.isoNow() } },
      });
    }
    for (const task of this.state.tasks.filter((t) => !isTerminal(t.status))) {
      this.emit({ type: "task.cancelled", task_id: task.id, data: {} });
    }
    this.emit({ type: "run.cancelled", data: {} });
  }

  resolveApproval(approvalId: ID, decision: ApprovalDecision): ApprovalRequest {
    const approval = this.state.approvals.find((a) => a.id === approvalId);
    if (!approval) throw new ApiError(404, "Approval request not found.");
    if (approval.status !== "pending") throw new ApiError(409, `This request was already ${approval.status}.`);

    const resolved: ApprovalRequest = {
      ...approval,
      status: decision === "approve" ? "approved" : "rejected",
      resolved_at: this.isoNow(),
    };
    this.emit({ type: "approval.resolved", task_id: approval.task_id, data: { approval: resolved } });

    if (decision === "approve") {
      this.startTask(this.task(approval.task_id));
    } else {
      this.emit({
        type: "task.skipped",
        task_id: approval.task_id,
        data: { reason: "You rejected this action, so nothing was sent." },
      });
      this.advance();
    }
    return resolved;
  }

  // -------------------------------------------------------------------------

  /** Moves the graph forward: skip blocked tasks, start ready ones, finish the run when done. */
  private advance(): void {
    if (this.state.status === "cancelled") return;

    // Skipping can unblock-by-skipping further dependants, so repeat until stable.
    let blocked = blockedTasks(this.state.tasks);
    while (blocked.length) {
      for (const { task, blocker } of blocked) {
        this.emit({
          type: "task.skipped",
          task_id: task.id,
          data: { reason: `Skipped because "${blocker.title}" didn't complete.` },
        });
      }
      blocked = blockedTasks(this.state.tasks);
    }

    for (const task of readyTasks(this.state.tasks)) {
      if (task.requires_approval) this.requestApproval(task);
      else this.startTask(task);
    }

    if (this.state.tasks.every((t) => isTerminal(t.status))) this.finish();
  }

  private requestApproval(task: WorkflowTask): void {
    const approval: ApprovalRequest = {
      id: this.options.newId("apr"),
      run_id: this.state.id,
      task_id: task.id,
      tool_name: task.tool_name,
      ...this.options.approvalFor(task, this.state),
      status: "pending",
      created_at: this.isoNow(),
      resolved_at: null,
    };
    this.emit({ type: "approval.requested", task_id: task.id, data: { approval } });
  }

  private startTask(task: WorkflowTask): void {
    this.emit({ type: "task.started", task_id: task.id, data: {} });
    const duration = this.options.durationFor(task);
    const timer = this.options.scheduler.setTimeout(() => this.finishTask(task.id, duration), duration);
    this.timers.set(task.id, timer);
  }

  private finishTask(taskId: ID, duration: number): void {
    this.timers.delete(taskId);
    const task = this.task(taskId);
    const upstream = task.depends_on.map((id) => this.task(id));
    const result = this.options.execute(task, upstream);

    if (result.ok) {
      this.emit({ type: "task.completed", task_id: taskId, data: { result, duration_ms: duration } });
    } else {
      const reason = result.error?.message ?? "The tool failed.";
      this.emit({ type: "task.failed", task_id: taskId, data: { result, duration_ms: duration, reason } });
    }
    this.advance();
  }

  private finish(): void {
    const failed = this.state.tasks.filter((t) => t.status === "failed");
    if (failed.length) {
      const names = failed.map((t) => `"${t.title}"`).join(", ");
      this.emit({ type: "run.failed", data: { reason: `${names} failed, so the run couldn't finish.` } });
    } else {
      this.emit({ type: "run.completed", data: { summary: this.options.summarize(this.state) } });
    }
  }

  private task(id: ID): WorkflowTask {
    return this.state.tasks.find((t) => t.id === id)!;
  }

  private isoNow(): string {
    return new Date(this.options.scheduler.now()).toISOString();
  }

  private emit(body: EventBody): void {
    const event = {
      id: this.history.length + 1,
      run_id: this.state.id,
      timestamp: this.isoNow(),
      task_id: body.task_id ?? null,
      type: body.type,
      data: body.data,
    } as WorkflowEvent;
    this.state = applyEvent(this.state, event);
    this.history.push(event);
    this.listeners.forEach((listener) => listener(event));
  }
}
