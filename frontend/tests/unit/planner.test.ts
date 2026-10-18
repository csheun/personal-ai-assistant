import { describe, expect, it } from "vitest";

import { planFromMessage } from "@/lib/api/mock/planner";
import { validateDag } from "@/lib/workflow/graph";

describe("mock planner", () => {
  it("plans a parallel briefing that needs approval to send", () => {
    const outcome = planFromMessage("Give me a morning briefing and send it to Telegram");
    if (outcome.kind !== "plan") throw new Error("expected a plan");
    const { tasks } = outcome.plan;

    expect(tasks.map((t) => t.tool_name)).toEqual([
      "get_weather",
      "calendar_list_events",
      "gmail_search",
      "summarize",
      "telegram_send_message",
    ]);
    expect(tasks.slice(0, 3).every((t) => t.depends_on.length === 0)).toBe(true);
    expect(tasks[3].depends_on).toEqual(["t1", "t2", "t3"]);
    expect(tasks[4]).toMatchObject({ depends_on: ["t4"], requires_approval: true });
    expect(tasks.filter((t) => t.requires_approval)).toHaveLength(1);
    expect(() => validateDag(tasks)).not.toThrow();
  });

  it("extracts the city", () => {
    const outcome = planFromMessage("Will it rain in Kuala Lumpur?");
    expect(outcome.kind === "plan" && outcome.plan.tasks[0].arguments).toEqual({ city: "Kuala Lumpur" });
  });

  it("answers directly when no tool is needed", () => {
    expect(planFromMessage("hello there").kind).toBe("reply");
  });

  it("supports simulated errors and failures", () => {
    expect(planFromMessage("simulate error")).toMatchObject({ kind: "error", status: 503 });
    const outcome = planFromMessage("weather, simulate failure");
    expect(outcome.kind === "plan" && outcome.plan.failTaskIds).toEqual(["t1"]);
  });
});
