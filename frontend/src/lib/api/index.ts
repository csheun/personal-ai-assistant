import type { ApiClient } from "./client";
import { MockApiClient } from "./mock/mock-client";

/**
 * The one place that decides which backend the UI talks to.
 * When FastAPI is ready: `return new HttpApiClient(process.env.NEXT_PUBLIC_API_URL)`.
 */
export function createApiClient(): ApiClient {
  return new MockApiClient({ seed: true, speed: mockSpeed() });
}

/**
 * Multiplier for simulated durations: NEXT_PUBLIC_MOCK_SPEED, overridable per page
 * with `?mock_speed=3` (used by e2e tests to make in-flight states easy to observe).
 */
function mockSpeed(): number {
  const fromUrl = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("mock_speed");
  const speed = Number(fromUrl ?? process.env.NEXT_PUBLIC_MOCK_SPEED ?? "1");
  return Number.isFinite(speed) && speed > 0 && speed <= 20 ? speed : 1;
}

export type { ApiClient } from "./client";
export * from "./types";
