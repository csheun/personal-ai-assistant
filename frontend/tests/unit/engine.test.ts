import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowEvent } from "@/lib/api/types";
import { applyEvent } from "@/lib/workflow/reducer";
import { makeEngine, statuses } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-18T09:00:00Z"));
});
afterEach(() => vi.useRealTimers());

describe("status transitions", () => {
  it("moves a single task pending → running → completed and completes the run", () => {
    const engine = makeEngine([{ id: "a", ms: 500 }]);
    expect(engine.run.status).toBe("planned");
    expect(statuses(engine)).toEqual({ a: "pending" });

    engine.start();
    expect(engine.run.status).toBe("running");
    expect(statuses(engine)).toEqual({ a: "running" });

    vi.advanceTimersByTime(499);
    expect(statuses(engine)).toEqual({ a: "running" });
    vi.advanceTimersByTime(1);

    expect(statuses(engine)).toEqual({ a: "completed" });
    expect(engine.run.status).toBe("completed");
    expect(engine.run.summary).toBe("All done.");
    expect(engine.run.tasks[0].duration_ms).toBe(500);
    expect(engine.events.map((e) => e.type)).toEqual(["run.started", "task.started", "task.completed", "run.completed"]);
  });

  it("numbers events with a monotonic seq", () => {
    const engine = makeEngine([{ id: "a" }, { id: "b", deps: ["a"] }]);
    engine.start();
    vi.runAllTimers();
    expect(engine.events.map((e) => e.seq)).toEqual(engine.events.map((_, i) => i + 1));
  });

  it("refuses to start twice", () => {
    const engine = makeEngine([{ id: "a" }]);
    engine.start();
    expect(() => engine.start()).toThrow(/already started/);
  });

  it("fails the run and skips dependants when a task fails", () => {
    const engine = makeEngine([{ id: "a", fail: true }, { id: "b" }, { id: "c", deps: ["a", "b"] }, { id: "d", deps: ["c"] }]);
    engine.start();
    vi.runAllTimers();

    expect(statuses(engine)).toEqual({ a: "failed", b: "completed", c: "skipped", d: "skipped" });
    expect(engine.run.status).toBe("failed");
    expect(engine.run.tasks[2].status_reason).toContain("Task a");
    expect(engine.run.tasks[0].status_reason).toBe("boom");
  });
});

describe("dependency ordering and concurrency", () => {
  it("starts independent tasks together", () => {
    const engine = makeEngine([{ id: "a", ms: 1000 }, { id: "b", ms: 3000 }, { id: "c", ms: 2000 }]);
    engine.start();
    expect(statuses(engine)).toEqual({ a: "running", b: "running", c: "running" });

    vi.runAllTimers();
    // Wall-clock time is the longest task, not the sum.
    const wall = Date.parse(engine.run.finished_at!) - Date.parse(engine.run.started_at!);
    expect(wall).toBe(3000);
  });

  it("waits for every dependency before starting a task", () => {
    const engine = makeEngine([{ id: "a", ms: 1000 }, { id: "b", ms: 2500 }, { id: "c", deps: ["a", "b"], ms: 500 }]);
    engine.start();

    vi.advanceTimersByTime(1000);
    expect(statuses(engine)).toEqual({ a: "completed", b: "running", c: "pending" });

    vi.advanceTimersByTime(1500);
    expect(statuses(engine)).toEqual({ a: "completed", b: "completed", c: "running" });

    vi.runAllTimers();
    const [a, b, c] = engine.run.tasks;
    expect(Date.parse(c.started_at!)).toBeGreaterThanOrEqual(Date.parse(a.finished_at!));
    expect(Date.parse(c.started_at!)).toBeGreaterThanOrEqual(Date.parse(b.finished_at!));
  });

  it("runs a diamond in the right order", () => {
    const engine = makeEngine([
      { id: "root", ms: 100 },
      { id: "left", deps: ["root"], ms: 300 },
      { id: "right", deps: ["root"], ms: 200 },
      { id: "join", deps: ["left", "right"], ms: 100 },
    ]);
    engine.start();
    vi.runAllTimers();

    const started = engine.events.filter((e) => e.type === "task.started").map((e) => (e as { task_id: string }).task_id);
    expect(started).toEqual(["root", "left", "right", "join"]);
    expect(engine.run.status).toBe("completed");
  });

  it("rejects invalid graphs", () => {
    expect(() => makeEngine([{ id: "a", deps: ["b"] }, { id: "b", deps: ["a"] }])).toThrow(/cycle/);
    expect(() => makeEngine([{ id: "a", deps: ["missing"] }])).toThrow(/unknown task/);
  });
});

describe("approval", () => {
  const specs = [{ id: "sum", ms: 100 }, { id: "send", deps: ["sum"], approval: true, ms: 200 }];

  it("pauses for approval and runs the task after approving", () => {
    const engine = makeEngine(specs);
    engine.start();
    vi.advanceTimersByTime(100);

    expect(statuses(engine)).toEqual({ sum: "completed", send: "waiting_for_approval" });
    expect(engine.run.status).toBe("waiting_for_approval");
    const [approval] = engine.run.approvals;
    expect(approval).toMatchObject({ status: "pending", task_id: "send", preview: { body: "Hello" } });

    // Nothing happens while waiting, however long it takes.
    vi.advanceTimersByTime(60_000);
    expect(statuses(engine).send).toBe("waiting_for_approval");

    engine.resolveApproval(approval.id, "approve");
    expect(engine.run.approvals[0].status).toBe("approved");
    expect(engine.run.status).toBe("running");
    expect(statuses(engine).send).toBe("running");

    vi.runAllTimers();
    expect(statuses(engine).send).toBe("completed");
    expect(engine.run.status).toBe("completed");
  });

  it("skips the task when rejected, and the run still completes", () => {
    const engine = makeEngine(specs);
    engine.start();
    vi.advanceTimersByTime(100);

    engine.resolveApproval(engine.run.approvals[0].id, "reject");

    expect(engine.run.approvals[0].status).toBe("rejected");
    expect(statuses(engine).send).toBe("skipped");
    expect(engine.run.tasks[1].status_reason).toMatch(/rejected/);
    expect(engine.run.tasks[1].started_at).toBeNull(); // the action never ran
    expect(engine.run.status).toBe("completed");
  });

  it("refuses to resolve the same request twice or an unknown one", () => {
    const engine = makeEngine(specs);
    engine.start();
    vi.advanceTimersByTime(100);
    const id = engine.run.approvals[0].id;
    engine.resolveApproval(id, "reject");

    expect(() => engine.resolveApproval(id, "approve")).toThrow(/already rejected/);
    expect(() => engine.resolveApproval("nope", "approve")).toThrow(/not found/);
  });

  it("keeps other branches running while one waits for approval", () => {
    const engine = makeEngine([
      { id: "send", approval: true },
      { id: "slow", ms: 1000 },
    ]);
    engine.start();
    expect(statuses(engine)).toEqual({ send: "waiting_for_approval", slow: "running" });
    vi.advanceTimersByTime(1000);
    expect(statuses(engine).slow).toBe("completed");
    expect(engine.run.status).toBe("waiting_for_approval");
  });
});

describe("cancellation", () => {
  it("cancels running and pending tasks and stops the clock", () => {
    const engine = makeEngine([{ id: "a", ms: 500 }, { id: "b", ms: 2000 }, { id: "c", deps: ["a", "b"] }]);
    engine.start();
    vi.advanceTimersByTime(500);
    engine.cancel();

    expect(statuses(engine)).toEqual({ a: "completed", b: "cancelled", c: "cancelled" });
    expect(engine.run.status).toBe("cancelled");
    expect(engine.run.tasks[1].duration_ms).toBe(500); // ran for 500ms before cancel

    const count = engine.events.length;
    vi.runAllTimers();
    expect(engine.events.length).toBe(count); // no late completions
  });

  it("expires an open approval request", () => {
    const engine = makeEngine([{ id: "send", approval: true }]);
    engine.start();
    engine.cancel();

    expect(engine.run.approvals[0].status).toBe("expired");
    expect(statuses(engine).send).toBe("cancelled");
    expect(() => engine.resolveApproval(engine.run.approvals[0].id, "approve")).toThrow(/already expired/);
  });

  it("can cancel a planned run before it starts", () => {
    const engine = makeEngine([{ id: "a" }]);
    engine.cancel();
    expect(engine.run.status).toBe("cancelled");
    expect(engine.run.tasks[0].duration_ms).toBeNull();
  });

  it("refuses to cancel a finished run", () => {
    const engine = makeEngine([{ id: "a" }]);
    engine.start();
    vi.runAllTimers();
    expect(() => engine.cancel()).toThrow(/already finished/);
  });
});

describe("event stream", () => {
  it("replays history to late subscribers, and replaying reproduces the run", () => {
    const engine = makeEngine([{ id: "a", ms: 100 }, { id: "b", deps: ["a"], approval: true }]);
    const initial = engine.run;
    engine.start();
    vi.advanceTimersByTime(100);

    const received: WorkflowEvent[] = [];
    engine.subscribe((e) => received.push(e));
    expect(received.map((e) => e.type)).toEqual(["run.started", "task.started", "task.completed", "approval.requested"]);

    engine.resolveApproval(engine.run.approvals[0].id, "approve");
    vi.runAllTimers();

    expect(received.at(-1)?.type).toBe("run.completed");
    expect(received.reduce(applyEvent, initial)).toEqual(engine.run);
  });

  it("stops delivering after unsubscribe", () => {
    const engine = makeEngine([{ id: "a" }]);
    const received: WorkflowEvent[] = [];
    const unsubscribe = engine.subscribe((e) => received.push(e));
    unsubscribe();
    engine.start();
    expect(received).toEqual([]);
  });
});

describe("resuming a stream", () => {
  it("replays only events after afterSeq", () => {
    const engine = makeEngine([{ id: "a", ms: 100 }, { id: "b", deps: ["a"], ms: 100 }]);
    engine.start();
    vi.advanceTimersByTime(100);
    const snapshot = engine.run;

    const received: WorkflowEvent[] = [];
    engine.subscribe((e) => received.push(e), snapshot.last_event_seq);
    vi.runAllTimers();

    expect(received[0].seq).toBe(snapshot.last_event_seq + 1);
    expect(received.reduce(applyEvent, snapshot)).toEqual(engine.run);
  });
});
