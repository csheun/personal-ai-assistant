import { describe, expect, it } from "vitest";

import { describePlanning, elapsedMs, failureReason, progress, summarySources, timelineBars } from "@/lib/workflow/metrics";
import { makeRun } from "./helpers";

const t0 = Date.parse("2026-10-18T09:00:00Z");
const iso = (ms: number) => new Date(t0 + ms).toISOString();

describe("metrics", () => {
  const run = makeRun([{ id: "a" }, { id: "b" }, { id: "c", deps: ["a", "b"] }]);
  run.started_at = iso(0);
  run.status = "running";
  run.tasks[0] = { ...run.tasks[0], status: "completed", started_at: iso(0), finished_at: iso(2000), duration_ms: 2000 };
  run.tasks[1] = { ...run.tasks[1], status: "running", started_at: iso(0) };

  it("reports progress and elapsed time", () => {
    expect(progress(run)).toEqual({ done: 1, total: 3 });
    expect(elapsedMs(run, t0 + 5000)).toBe(5000);
    expect(elapsedMs({ ...run, finished_at: iso(6000) }, t0 + 99_000)).toBe(6000);
  });

  it("places concurrent tasks side by side on the time axis", () => {
    const { bars, spanMs } = timelineBars(run, t0 + 8000);
    expect(spanMs).toBe(8000);
    expect(bars.map((b) => b.work)).toEqual([{ offset: 0, width: 0.25 }, { offset: 0, width: 1 }, null]);
  });

  it("keeps the approval wait on the timeline after it is resolved", () => {
    const withApproval = {
      ...run,
      approvals: [
        {
          id: "apr", run_id: run.id, task_id: "c", tool_name: "telegram_send_message" as const, action: "", status: "approved" as const,
          preview: { destination: "", body: "" }, created_at: iso(2000), resolved_at: iso(6000),
        },
      ],
      tasks: run.tasks.map((t) => (t.id === "c" ? { ...t, status: "running" as const, started_at: iso(6000) } : t)),
    };
    const c = timelineBars(withApproval, t0 + 8000).bars[2];
    expect(c.wait).toEqual({ offset: 0.25, width: 0.5 });
    expect(c.work).toEqual({ offset: 0.75, width: 0.25 });
  });

  it("explains failures", () => {
    const failed = { ...run, status: "failed" as const, tasks: [{ ...run.tasks[0], status: "failed" as const, status_reason: "boom" }] };
    expect(failureReason(failed)).toBe("Task a: boom");
  });
});

describe("summary sources and planning description", () => {
  const base = makeRun([{ id: "s", tool: "summarize" }]);
  const withSources = (sources: unknown) => ({
    ...base,
    tasks: [
      {
        ...base.tasks[0],
        result: { tool_name: "summarize" as const, arguments: {}, ok: true, output: { text: "x", sources }, error: null, mocked: false },
      },
    ],
  });

  it("returns only well-formed http(s) citations", () => {
    const run = withSources([
      { ref: 1, title: "A", url: "https://a.example/x" },
      { ref: 2, title: "Bad", url: "javascript:alert(1)" },
      { ref: "3", title: "Wrong type", url: "https://c.example" },
    ]);
    expect(summarySources(run)).toEqual([{ ref: 1, title: "A", url: "https://a.example/x" }]);
    expect(summarySources(base)).toEqual([]);
  });

  it("describes how a run was planned", () => {
    expect(describePlanning(null)).toBeNull();
    expect(describePlanning({ planner: "mock", attempts: 0, duration_ms: 0, usage: [] })).toMatch(/demo planner/);
    const usage = { purpose: "plan", provider: "groq", model: "openai/gpt-oss-120b", duration_ms: 2250, input_tokens: 1777, output_tokens: 822 };
    expect(describePlanning({ planner: "llm", attempts: 2, duration_ms: 2250, usage: [usage] })).toBe(
      "Planned by groq:openai/gpt-oss-120b in 2.3s, 2,599 tokens, 2 attempts",
    );
  });
});
