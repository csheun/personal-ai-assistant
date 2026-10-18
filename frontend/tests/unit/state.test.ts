import { describe, expect, it } from "vitest";

import type { WorkflowEvent } from "@/lib/api/types";
import { assistantReducer, initialState } from "@/lib/state/assistant-state";
import { makeRun } from "./helpers";

describe("assistant state", () => {
  const run = makeRun([{ id: "a" }]);
  const started = { ...run, status: "running" as const, last_event_id: 2 };
  const withRun = assistantReducer(initialState, { type: "run/loaded", run });
  const event = (id: number): WorkflowEvent => ({
    id,
    run_id: run.id,
    timestamp: "2026-10-18T09:00:00Z",
    task_id: null,
    type: "run.started",
    data: {},
  });

  it("applies newer snapshots and ignores older ones", () => {
    const newer = assistantReducer(withRun, { type: "run/loaded", run: started });
    expect(newer.runs[run.id].status).toBe("running");
    const stale = assistantReducer(newer, { type: "run/loaded", run });
    expect(stale.runs[run.id]).toBe(newer.runs[run.id]);
  });

  it("drops events already reflected in the snapshot", () => {
    const state = assistantReducer(withRun, { type: "run/loaded", run: started });
    expect(assistantReducer(state, { type: "run/event", event: event(2) })).toBe(state);
    expect(assistantReducer(state, { type: "run/event", event: event(3) }).runs[run.id].last_event_id).toBe(3);
  });

  it("tracks stream status per run", () => {
    const state = assistantReducer(withRun, { type: "run/stream", runId: run.id, status: "reconnecting" });
    expect(state.streams[run.id]).toBe("reconnecting");
  });
});
