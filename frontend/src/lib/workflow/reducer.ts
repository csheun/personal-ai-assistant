import type { WorkflowEvent, WorkflowRun, WorkflowTask } from "@/lib/api/types";

/**
 * Applies one event to a run and returns the new run (never mutates).
 *
 * This is the single definition of how a run's state changes. The mock engine
 * uses it on its own state, and the UI uses it on streamed events, so both
 * always agree. When FastAPI sends the same events over SSE, this file does
 * not change.
 */
export function applyEvent(run: WorkflowRun, event: WorkflowEvent): WorkflowRun {
  return { ...reduce(run, event), last_event_seq: event.seq };
}

function reduce(run: WorkflowRun, event: WorkflowEvent): WorkflowRun {
  const updateTask = (id: string, patch: Partial<WorkflowTask>): WorkflowTask[] =>
    run.tasks.map((t) => (t.id === id ? { ...t, ...patch } : t));

  switch (event.type) {
    case "run.started":
      return { ...run, status: "running", started_at: event.timestamp };

    case "task.started":
      return {
        ...run,
        status: hasPendingApproval(run, event.task_id) ? "waiting_for_approval" : "running",
        tasks: updateTask(event.task_id, { status: "running", started_at: event.timestamp }),
      };

    case "task.completed":
      return {
        ...run,
        tasks: updateTask(event.task_id, {
          status: "completed",
          finished_at: event.timestamp,
          duration_ms: event.duration_ms,
          result: event.result,
        }),
      };

    case "task.failed":
      return {
        ...run,
        tasks: updateTask(event.task_id, {
          status: "failed",
          finished_at: event.timestamp,
          duration_ms: event.duration_ms,
          result: event.result,
          status_reason: event.reason,
        }),
      };

    case "task.skipped":
      return { ...run, tasks: updateTask(event.task_id, { status: "skipped", status_reason: event.reason }) };

    case "task.cancelled": {
      const task = run.tasks.find((t) => t.id === event.task_id);
      const ranFor = task?.started_at ? Date.parse(event.timestamp) - Date.parse(task.started_at) : null;
      return {
        ...run,
        tasks: updateTask(event.task_id, {
          status: "cancelled",
          finished_at: task?.started_at ? event.timestamp : null,
          duration_ms: ranFor,
          status_reason: "Stopped because you cancelled the run.",
        }),
      };
    }

    case "approval.requested":
      return {
        ...run,
        status: "waiting_for_approval",
        tasks: updateTask(event.task_id, { status: "waiting_for_approval" }),
        approvals: [...run.approvals, event.approval],
      };

    case "approval.resolved": {
      const approvals = run.approvals.map((a) => (a.id === event.approval.id ? event.approval : a));
      const stillWaiting = approvals.some((a) => a.status === "pending");
      return { ...run, approvals, status: stillWaiting || run.status !== "waiting_for_approval" ? run.status : "running" };
    }

    case "run.completed":
      return { ...run, status: "completed", summary: event.summary, finished_at: event.timestamp };

    case "run.failed":
      return { ...run, status: "failed", finished_at: event.timestamp };

    case "run.cancelled":
      return { ...run, status: "cancelled", finished_at: event.timestamp };
  }
}

function hasPendingApproval(run: WorkflowRun, exceptTaskId: string): boolean {
  return run.approvals.some((a) => a.status === "pending" && a.task_id !== exceptTaskId);
}
