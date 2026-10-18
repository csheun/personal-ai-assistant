import { WorkflowEngine } from "@/lib/api/mock/engine";
import type { ToolName, WorkflowRun, WorkflowTask } from "@/lib/api/types";

export interface TaskSpec {
  id: string;
  deps?: string[];
  ms?: number;
  approval?: boolean;
  fail?: boolean;
  tool?: ToolName;
}

export function makeRun(specs: TaskSpec[]): WorkflowRun {
  return {
    id: "run_test",
    conversation_id: "conv_test",
    goal: "test",
    status: "planned",
    created_at: new Date().toISOString(),
    started_at: null,
    finished_at: null,
    summary: null,
    approvals: [],
    last_event_id: 0,
    tasks: specs.map(
      (s): WorkflowTask => ({
        id: s.id,
        title: `Task ${s.id}`,
        tool_name: s.tool ?? (s.approval ? "telegram_send_message" : "web_search"),
        arguments: {},
        depends_on: s.deps ?? [],
        requires_approval: s.approval ?? false,
        status: "pending",
        started_at: null,
        finished_at: null,
        duration_ms: null,
        result: null,
        status_reason: null,
      }),
    ),
  };
}

/** Engine on the global (fake-able) timers, with per-task durations and failures. */
export function makeEngine(specs: TaskSpec[]): WorkflowEngine {
  const byId = new Map(specs.map((s) => [s.id, s]));
  let ids = 0;
  return new WorkflowEngine(makeRun(specs), {
    scheduler: {
      now: () => Date.now(),
      setTimeout: (fn, ms) => setTimeout(fn, ms),
      clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
    },
    durationFor: (t) => byId.get(t.id)?.ms ?? 1000,
    execute: (t) =>
      byId.get(t.id)?.fail
        ? { tool_name: t.tool_name, arguments: {}, ok: false, output: null, error: { code: "simulated_failure", message: "boom" }, mocked: true }
        : { tool_name: t.tool_name, arguments: {}, ok: true, output: { id: t.id }, error: null, mocked: true },
    approvalFor: () => ({ action: "Send it", preview: { destination: "Telegram", body: "Hello" } }),
    summarize: () => "All done.",
    newId: (p) => `${p}_${++ids}`,
  });
}

export const statuses = (engine: WorkflowEngine) =>
  Object.fromEntries(engine.run.tasks.map((t) => [t.id, t.status]));
