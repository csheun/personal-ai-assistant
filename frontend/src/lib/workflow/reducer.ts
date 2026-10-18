import type { WorkflowEvent, WorkflowRun, WorkflowTask } from "@/lib/api/types";

/**
 * Applies one event to a run and returns the new run (never mutates).
 *
 * The single definition of how a run's state changes on the client. The mock
 * engine uses it on its own state; the UI applies it to streamed events from
 * either the mock or FastAPI. Its Python twin is `backend/app/workflows/reducer.py`,
 * and tests/unit/contract.test.ts checks both produce identical snapshots.
 */
export function applyEvent(run: WorkflowRun, event: WorkflowEvent): WorkflowRun {
  return { ...reduce(run, event), last_event_id: event.id };
}

function reduce(run: WorkflowRun, event: WorkflowEvent): WorkflowRun {
  const updateTask = (patch: Partial<WorkflowTask>): WorkflowTask[] =>
    run.tasks.map((t) => (t.id === event.task_id ? { ...t, ...patch } : t));

  switch (event.type) {
    case "run.started":
      return { ...run, status: "running", started_at: event.timestamp };

    case "task.started": {
      const waiting = run.approvals.some((a) => a.status === "pending" && a.task_id !== event.task_id);
      return {
        ...run,
        status: waiting ? "waiting_for_approval" : "running",
        tasks: updateTask({ status: "running", started_at: event.timestamp }),
      };
    }

    case "task.completed":
      return {
        ...run,
        tasks: updateTask({
          status: "completed",
          finished_at: event.timestamp,
          duration_ms: event.data.duration_ms,
          result: event.data.result,
        }),
      };

    case "task.failed":
      return {
        ...run,
        tasks: updateTask({
          status: "failed",
          finished_at: event.timestamp,
          duration_ms: event.data.duration_ms,
          result: event.data.result,
          status_reason: event.data.reason,
        }),
      };

    case "task.skipped":
      return { ...run, tasks: updateTask({ status: "skipped", status_reason: event.data.reason }) };

    case "task.cancelled": {
      const task = run.tasks.find((t) => t.id === event.task_id);
      const started = task?.started_at ?? null;
      return {
        ...run,
        tasks: updateTask({
          status: "cancelled",
          finished_at: started ? event.timestamp : null,
          duration_ms: started ? Date.parse(event.timestamp) - Date.parse(started) : null,
          status_reason: "Stopped because you cancelled the run.",
        }),
      };
    }

    case "approval.requested":
      return {
        ...run,
        status: "waiting_for_approval",
        tasks: updateTask({ status: "waiting_for_approval" }),
        approvals: [...run.approvals, event.data.approval],
      };

    case "approval.resolved": {
      const approvals = run.approvals.map((a) => (a.id === event.data.approval.id ? event.data.approval : a));
      const stillWaiting = approvals.some((a) => a.status === "pending");
      return { ...run, approvals, status: stillWaiting || run.status !== "waiting_for_approval" ? run.status : "running" };
    }

    case "run.completed":
      return { ...run, status: "completed", summary: event.data.summary, finished_at: event.timestamp };

    case "run.failed":
      return { ...run, status: "failed", finished_at: event.timestamp };

    case "run.cancelled":
      return { ...run, status: "cancelled", finished_at: event.timestamp };
  }
}
