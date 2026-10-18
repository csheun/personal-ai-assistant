import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MockApiClient } from "@/lib/api/mock/mock-client";
import { ApiError, type WorkflowEvent } from "@/lib/api/types";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-18T09:00:00Z"));
});
afterEach(() => vi.useRealTimers());

/** Resolves a mock request by advancing past its simulated latency. */
async function settle<T>(promise: Promise<T>): Promise<T> {
  // Attach handlers before advancing time so a rejection is never "unhandled".
  const outcome = promise.then(
    (value) => ({ ok: true as const, value }),
    (error: unknown) => ({ ok: false as const, error }),
  );
  await vi.advanceTimersByTimeAsync(400);
  const result = await outcome;
  if (!result.ok) throw result.error;
  return result.value;
}

describe("MockApiClient", () => {
  it("creates a conversation with a planned run", async () => {
    const client = new MockApiClient();
    const res = await settle(client.sendMessage({ conversation_id: null, message: "Briefing please, send to Telegram" }));

    expect(res.conversation.title).toBe("Briefing please, send to Telegram");
    expect(res.assistant_message.run_id).toBe(res.run!.id);
    expect(res.run!.status).toBe("planned");
    expect(await settle(client.listConversations())).toHaveLength(1);
    expect(await settle(client.listMessages(res.conversation.id))).toHaveLength(2);
  });

  it("validates input like the API", async () => {
    const client = new MockApiClient();
    await expect(settle(client.sendMessage({ conversation_id: null, message: "  " }))).rejects.toMatchObject({ status: 422 });
    await expect(settle(client.sendMessage({ conversation_id: "nope", message: "hi" }))).rejects.toBeInstanceOf(ApiError);
    await expect(settle(client.sendMessage({ conversation_id: null, message: "simulate error" }))).rejects.toMatchObject({
      status: 503,
    });
  });

  it("runs end to end over the event stream, never sending for real", async () => {
    const client = new MockApiClient();
    const { run } = await settle(client.sendMessage({ conversation_id: null, message: "Briefing, send to Telegram" }));
    const events: WorkflowEvent[] = [];
    client.subscribeToRun(run!.id, (e) => events.push(e));

    await settle(client.startRun(run!.id));
    await vi.advanceTimersByTimeAsync(10_000);

    const approval = (await settle(client.getRun(run!.id))).approvals[0];
    expect(approval.preview.body).toContain("°C");
    await settle(client.resolveApproval(approval.id, "approve"));
    await vi.advanceTimersByTimeAsync(10_000);

    const finished = await settle(client.getRun(run!.id));
    expect(finished.status).toBe("completed");
    expect(finished.summary).toMatch(/nothing was actually sent/);
    const telegram = finished.tasks.find((t) => t.tool_name === "telegram_send_message")!;
    expect(telegram.result).toMatchObject({ mocked: true, output: { delivered: false } });
    expect(events.at(-1)?.type).toBe("run.completed");

    const stats = await settle(client.getStats());
    expect(stats).toMatchObject({ total_runs: 1, completed_runs: 1, approvals_approved: 1, tool_calls: 5 });
    // weather 900 / calendar 1300 / gmail 1700 run together → saves 900 + 1300.
    expect(stats.time_saved_by_parallelism_ms).toBe(2200);
  });

  it("seeds completed example conversations", async () => {
    const client = new MockApiClient({ seed: true });
    const conversations = await settle(client.listConversations());
    expect(conversations.map((c) => c.title)).toEqual([
      "Give me a morning briefing and send it to Telegram",
      "What's the weather in Tokyo and the latest news on…",
      "What can you do?",
    ]);
    const [first] = await settle(client.listMessages(conversations[0].id));
    expect(first.created_at).toBe("2026-10-16T23:40:00.000Z");
    const stats = await settle(client.getStats());
    expect(stats.completed_runs).toBe(2);
  });
});
