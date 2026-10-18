import { describe, expect, it, vi } from "vitest";

import type { StreamStatus } from "@/lib/api/client";
import { HttpWorkflowClient } from "@/lib/api/http-client";
import { ApiError, type WorkflowEvent } from "@/lib/api/types";

const BASE = "http://api.test";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Minimal EventSource stand-in that the test drives by hand. */
class FakeEventSource {
  static last: FakeEventSource;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  close() {
    this.closed = true;
  }
  emit(event: Partial<WorkflowEvent> & { id: number; type: string }) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ run_id: "r1", task_id: null, data: {}, ...event }) }));
  }
}

function client(fetchImpl: typeof fetch) {
  return new HttpWorkflowClient(BASE, {
    fetch: fetchImpl,
    eventSource: (url) => new FakeEventSource(url) as unknown as EventSource,
  });
}

describe("HttpWorkflowClient REST", () => {
  it("sends JSON to the FastAPI routes", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { status: "approved" }));
    await client(fetchMock as typeof fetch).resolveApproval("run 1", "apr_1", "reject");

    expect(fetchMock).toHaveBeenCalledWith(`${BASE}/api/workflows/run%201/approve`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: "apr_1", decision: "reject" }),
    });
  });

  it("turns FastAPI errors into ApiError with the server's message", async () => {
    const conflict = client((async () => jsonResponse(409, { detail: "This run has already finished." })) as typeof fetch);
    await expect(conflict.cancelRun("r1")).rejects.toEqual(new ApiError(409, "This run has already finished."));

    const invalid = client(
      (async () => jsonResponse(422, { detail: [{ msg: "String should have at least 1 character" }] })) as typeof fetch,
    );
    await expect(invalid.sendMessage({ conversation_id: null, message: "" })).rejects.toMatchObject({
      status: 422,
      message: "String should have at least 1 character",
    });
  });

  it("reports an unreachable server clearly", async () => {
    const down = client((async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch);
    await expect(down.listConversations()).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/backend is running/) });
  });
});

describe("HttpWorkflowClient event stream", () => {
  it("resumes after the given id, drops duplicates, and closes when the run ends", () => {
    const events: number[] = [];
    const statuses: StreamStatus[] = [];
    client(vi.fn() as unknown as typeof fetch).subscribeToRun(
      "r1",
      { onEvent: (e) => events.push(e.id), onStatusChange: (s) => statuses.push(s) },
      3,
    );
    const source = FakeEventSource.last;
    expect(source.url).toBe(`${BASE}/api/workflows/r1/events?after=3`);

    source.onopen?.();
    source.emit({ id: 3, type: "task.started" }); // already applied before subscribing
    source.emit({ id: 4, type: "task.started" });
    source.emit({ id: 4, type: "task.started" }); // replayed after a reconnect
    source.emit({ id: 5, type: "run.completed", data: { summary: "done" } });

    expect(events).toEqual([4, 5]);
    expect(source.closed).toBe(true);
    expect(statuses).toEqual(["connecting", "live", "closed"]);
  });

  it("shows reconnecting on errors, and stops once the finished run has been fully seen", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { status: "completed", last_event_id: 2 }));
    const statuses: StreamStatus[] = [];
    client(fetchMock as typeof fetch).subscribeToRun("r1", { onEvent: () => {}, onStatusChange: (s) => statuses.push(s) });
    const source = FakeEventSource.last;

    source.emit({ id: 1, type: "run.started" });
    source.emit({ id: 2, type: "task.started" });
    source.onerror?.();
    expect(statuses.at(-1)).toBe("reconnecting");

    await vi.waitFor(() => expect(source.closed).toBe(true));
    expect(statuses.at(-1)).toBe("closed");
  });

  it("keeps reconnecting while the run is still going", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { status: "running", last_event_id: 9 }));
    client(fetchMock as typeof fetch).subscribeToRun("r1", { onEvent: () => {} });
    const source = FakeEventSource.last;
    source.onerror?.();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(source.closed).toBe(false);
  });
});

describe("HttpWorkflowClient connection status", () => {
  it("reports offline when the server can't be reached and online once it answers again", async () => {
    vi.useFakeTimers();
    try {
      let up = false;
      const fetchMock = vi.fn(async () => {
        if (!up) throw new TypeError("Failed to fetch");
        return jsonResponse(200, { status: "ok" });
      });
      const seen: string[] = [];
      const stop = client(fetchMock as typeof fetch).watchConnection((s) => seen.push(s));

      await vi.advanceTimersByTimeAsync(0);
      expect(seen).toEqual(["checking", "offline"]);
      expect(fetchMock).toHaveBeenLastCalledWith(`${BASE}/health`, expect.anything());

      up = true;
      await vi.advanceTimersByTimeAsync(3_000); // retries quickly while offline
      expect(seen.at(-1)).toBe("online");

      stop();
      const calls = fetchMock.mock.calls.length;
      await vi.advanceTimersByTimeAsync(60_000);
      expect(fetchMock.mock.calls.length).toBe(calls); // no polling once nobody watches
    } finally {
      vi.useRealTimers();
    }
  });

  it("any failed request flips the status to offline immediately", async () => {
    const api = client((async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch);
    const seen: string[] = [];
    api.watchConnection((s) => seen.push(s));
    await api.listConversations().catch(() => {});
    expect(seen).toContain("offline");
  });
});

it("retries quickly after going offline even if the last check was a relaxed online one", async () => {
  vi.useFakeTimers();
  try {
    let up = true;
    const fetchMock = vi.fn(async () => {
      if (!up) throw new TypeError("Failed to fetch");
      return jsonResponse(200, []);
    });
    const api = client(fetchMock as typeof fetch);
    const seen: string[] = [];
    api.watchConnection((s) => seen.push(s));
    await vi.advanceTimersByTimeAsync(0);
    expect(seen.at(-1)).toBe("online"); // next health check is 5s away

    up = false;
    await api.listConversations().catch(() => {});
    expect(seen.at(-1)).toBe("offline");

    up = true;
    await vi.advanceTimersByTimeAsync(3_000);
    expect(seen.at(-1)).toBe("online");
  } finally {
    vi.useRealTimers();
  }
});
