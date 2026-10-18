import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { WorkflowEvent, WorkflowRun } from "@/lib/api/types";
import { applyEvent } from "@/lib/workflow/reducer";

/**
 * `contracts/workflow-scenarios.json` is recorded from the real Python runner
 * (backend/tests/contract_scenarios.py). Replaying its events through the TypeScript
 * reducer must give exactly the backend's final snapshot: if the two reducers or the
 * two schemas drift apart, this fails.
 */
const fixture = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../contracts/workflow-scenarios.json", import.meta.url)), "utf8"),
) as { scenarios: { name: string; initial: WorkflowRun; events: WorkflowEvent[]; final: WorkflowRun }[] };

describe("contract with the FastAPI backend", () => {
  it("covers every scenario", () => {
    expect(fixture.scenarios.map((s) => s.name)).toEqual(["approve", "reject", "cancel", "failure"]);
  });

  for (const scenario of fixture.scenarios) {
    it(`replays the "${scenario.name}" event stream to the backend's snapshot`, () => {
      const replayed = scenario.events.reduce(applyEvent, scenario.initial);
      expect(replayed).toEqual(scenario.final);
    });
  }

  it("resuming from a mid-run snapshot gives the same result", () => {
    const { initial, events, final } = fixture.scenarios[0];
    const midpoint = events.slice(0, 6).reduce(applyEvent, initial);
    const resumed = events.filter((e) => e.id > midpoint.last_event_id).reduce(applyEvent, midpoint);
    expect(resumed).toEqual(final);
  });
});
