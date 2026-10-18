import { describe, expect, it } from "vitest";

import { blockedTasks, dependencyLevels, groupByLevel, readyTasks, validateDag } from "@/lib/workflow/graph";
import { makeRun } from "./helpers";

describe("graph", () => {
  const tasks = makeRun([
    { id: "weather" },
    { id: "calendar" },
    { id: "summary", deps: ["weather", "calendar"] },
    { id: "send", deps: ["summary"] },
  ]).tasks;

  it("computes dependency levels", () => {
    expect(Object.fromEntries(dependencyLevels(tasks))).toEqual({ weather: 0, calendar: 0, summary: 1, send: 2 });
    expect(groupByLevel(tasks).map((g) => g.map((t) => t.id))).toEqual([["weather", "calendar"], ["summary"], ["send"]]);
  });

  it("finds ready and blocked tasks", () => {
    expect(readyTasks(tasks).map((t) => t.id)).toEqual(["weather", "calendar"]);

    const afterFailure = tasks.map((t) => (t.id === "weather" ? { ...t, status: "failed" as const } : t));
    expect(blockedTasks(afterFailure).map((b) => [b.task.id, b.blocker.id])).toEqual([["summary", "weather"]]);
  });

  it("validates", () => {
    expect(() => validateDag(tasks)).not.toThrow();
    expect(() => validateDag(makeRun([{ id: "a", deps: ["a"] }]).tasks)).toThrow(/cycle/);
    expect(() => validateDag(makeRun([{ id: "a" }, { id: "a" }]).tasks)).toThrow(/Duplicate/);
  });
});
