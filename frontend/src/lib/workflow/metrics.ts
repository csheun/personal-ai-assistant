import type { ApprovalRequest, Citation, ID, PlanningInfo, WorkflowRun, WorkflowTask } from "@/lib/api/types";
import { isTerminal } from "./graph";

export function progress(run: WorkflowRun): { done: number; total: number } {
  return { done: run.tasks.filter((t) => isTerminal(t.status)).length, total: run.tasks.length };
}

/** Wall-clock time since the run started; frozen once it finishes. */
export function elapsedMs(run: WorkflowRun, now: number | null): number | null {
  if (!run.started_at) return null;
  const end = run.finished_at ? Date.parse(run.finished_at) : now;
  return end === null ? null : Math.max(0, end - Date.parse(run.started_at));
}

export function pendingApproval(run: WorkflowRun): ApprovalRequest | null {
  return run.approvals.find((a) => a.status === "pending") ?? null;
}

export function failureReason(run: WorkflowRun): string | null {
  if (run.status !== "failed") return null;
  const failed = run.tasks.filter((t) => t.status === "failed");
  return failed.map((t) => `${t.title}: ${t.status_reason ?? "failed"}`).join(" ") || "The run failed.";
}

export interface Segment {
  /** Fractions of the timeline width, 0–1. */
  offset: number;
  width: number;
}

export interface TimelineBar {
  task: WorkflowTask;
  /** Time spent waiting for the user's approval (hatched in the UI). */
  wait: Segment | null;
  /** Time spent actually running. */
  work: Segment | null;
  /** Running time only; waiting for approval doesn't count. */
  durationMs: number | null;
}

/**
 * Lays tasks out on a shared time axis from run start to now (or run end).
 * Approval waits stay visible after they end, so gaps in the timeline are explained.
 */
export function timelineBars(run: WorkflowRun, now: number | null): { bars: TimelineBar[]; spanMs: number } {
  const start = run.started_at ? Date.parse(run.started_at) : null;
  const end = run.finished_at ? Date.parse(run.finished_at) : now;
  if (start === null || end === null) {
    return { bars: run.tasks.map((task) => ({ task, wait: null, work: null, durationMs: null })), spanMs: 0 };
  }
  // Minimum span keeps the first second from looking like a full-width bar.
  const spanMs = Math.max(end - start, 4000);
  const frac = (ms: number) => Math.min(1, Math.max(0, ms / spanMs));
  const segment = (from: number, to: number): Segment => ({ offset: frac(from - start), width: frac(to - from) });

  const bars = run.tasks.map((task): TimelineBar => {
    const approval = run.approvals.find((a) => a.task_id === task.id);
    const wait = approval
      ? segment(Date.parse(approval.created_at), approval.resolved_at ? Date.parse(approval.resolved_at) : end)
      : null;
    if (!task.started_at) return { task, wait, work: null, durationMs: null };
    const from = Date.parse(task.started_at);
    const to = task.finished_at ? Date.parse(task.finished_at) : end;
    return { task, wait, work: segment(from, to), durationMs: task.duration_ms ?? to - from };
  });
  return { bars, spanMs };
}

/**
 * Time parallel execution saved on one run: total task time minus the critical
 * path (the longest chain of dependent tasks). Unlike wall-clock time, this
 * ignores time spent waiting for the user's approval.
 */
export function parallelSavingMs(tasks: WorkflowTask[]): number {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const finishAt = new Map<ID, number>();
  const finish = (task: WorkflowTask): number => {
    const known = finishAt.get(task.id);
    if (known !== undefined) return known;
    const start = Math.max(0, ...task.depends_on.map((id) => finish(byId.get(id)!)));
    const value = start + (task.duration_ms ?? 0);
    finishAt.set(task.id, value);
    return value;
  };
  const criticalPath = Math.max(0, ...tasks.map(finish));
  const totalWork = tasks.reduce((sum, t) => sum + (t.duration_ms ?? 0), 0);
  return totalWork - criticalPath;
}

/** Web sources cited by the run's summary step (only http(s) links). */
export function summarySources(run: WorkflowRun): Citation[] {
  const summary = run.tasks.find((t) => t.tool_name === "summarize" && t.result?.ok);
  const sources = (summary?.result?.output as { sources?: unknown } | null | undefined)?.sources;
  if (!Array.isArray(sources)) return [];
  return sources.filter(
    (s): s is Citation =>
      !!s && typeof s.url === "string" && /^https?:\/\//.test(s.url) && typeof s.ref === "number",
  );
}

/** "Planned by groq:openai/gpt-oss-120b in 2.3s, 2,566 tokens" or the demo planner. */
export function describePlanning(planning: PlanningInfo | null | undefined): string | null {
  if (!planning) return null;
  if (planning.planner === "mock") return "Planned by the demo planner (keyword rules)";
  const model = planning.usage[0] ? `${planning.usage[0].provider}:${planning.usage[0].model}` : "the LLM";
  const tokens = planning.usage.reduce((sum, u) => sum + (u.input_tokens ?? 0) + (u.output_tokens ?? 0), 0);
  const seconds = (planning.duration_ms / 1000).toFixed(1);
  const attempts = planning.attempts > 1 ? `, ${planning.attempts} attempts` : "";
  return `Planned by ${model} in ${seconds}s${tokens ? `, ${tokens.toLocaleString("en-US")} tokens` : ""}${attempts}`;
}
