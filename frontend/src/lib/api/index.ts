import type { WorkflowClient } from "./client";
import { HttpWorkflowClient } from "./http-client";
import { MockWorkflowClient } from "./mock/mock-client";

/**
 * The one place that decides which backend the UI talks to.
 *
 * NEXT_PUBLIC_API_MODE=http  → FastAPI at NEXT_PUBLIC_API_URL (default http://localhost:8000)
 * NEXT_PUBLIC_API_MODE=mock  → everything simulated in the browser (default when unset)
 */
export function createWorkflowClient(): WorkflowClient {
  if (process.env.NEXT_PUBLIC_API_MODE === "http") {
    return new HttpWorkflowClient((process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, ""));
  }
  return new MockWorkflowClient({ seed: true, speed: mockSpeed() });
}

export const apiMode = (): "http" | "mock" => (process.env.NEXT_PUBLIC_API_MODE === "http" ? "http" : "mock");

/**
 * Mock mode only: multiplier for simulated durations, from NEXT_PUBLIC_MOCK_SPEED or
 * `?mock_speed=3` (used by e2e tests to make in-flight states easy to observe).
 */
function mockSpeed(): number {
  const fromUrl = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("mock_speed");
  const speed = Number(fromUrl ?? process.env.NEXT_PUBLIC_MOCK_SPEED ?? "1");
  return Number.isFinite(speed) && speed > 0 && speed <= 20 ? speed : 1;
}

export type { ConnectionStatus, RunStreamHandlers, StreamStatus, WorkflowClient } from "./client";
export * from "./types";
