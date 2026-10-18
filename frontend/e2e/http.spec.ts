import { expect, test } from "@playwright/test";

import { send, sendSuggestion, task } from "./helpers";

/** HTTP mode only: behaviour that depends on a real server. */

const BRIEFING = "Give me a morning briefing and send it to Telegram";

test("a refresh mid-run restores the run from the server and keeps streaming", async ({ page }) => {
  await sendSuggestion(page, BRIEFING);
  const panel = page.locator("#run-panel");
  await panel.getByRole("button", { name: "Run plan" }).click();
  await expect(task(panel, "t5")).toHaveAttribute("data-status", "waiting_for_approval", { timeout: 10_000 });
  await expect(page).toHaveURL(/\?c=conv_/);

  await page.reload();

  // Snapshot from GET /api/workflows/{id}, then the stream resumes after its last_event_id.
  await expect(task(panel, "t1")).toHaveAttribute("data-status", "completed");
  const approval = panel.getByRole("region", { name: "Send this to Telegram?" });
  await approval.getByRole("button", { name: "Approve and send" }).click();
  await expect(task(panel, "t5")).toHaveAttribute("data-status", "completed");
  await expect(panel.getByRole("region", { name: "Summary" })).toContainText("nothing was actually sent");
});

test("a dropped event stream shows reconnecting and then catches up", async ({ page }) => {
  // Block the SSE endpoint: the run still executes on the server.
  await page.route("**/api/workflows/*/events*", (route) => route.abort());
  await sendSuggestion(page, BRIEFING);
  const panel = page.locator("#run-panel");
  await panel.getByRole("button", { name: "Run plan" }).click();
  // The start response's snapshot shows the run as running even though no events get through.
  await expect(panel.getByText("Lost the live connection")).toBeVisible();

  // Connection comes back: EventSource retries and the server replays everything missed.
  await page.unroute("**/api/workflows/*/events*");
  await expect(task(panel, "t5")).toHaveAttribute("data-status", "waiting_for_approval", { timeout: 15_000 });
  await expect(panel.getByText("Lost the live connection")).toBeHidden();
});

test("shows a clear error when the backend is unreachable", async ({ page }) => {
  await page.route("**/api/chat", (route) => route.abort("connectionrefused"));
  await page.goto("/");
  await send(page, "What's the weather in Paris?");
  const alert = page.getByRole("alert").filter({ hasText: "Message not sent" });
  await expect(alert).toContainText("Can't reach the assistant server");

  await page.unroute("**/api/chat");
  await alert.getByRole("button", { name: "Send again" }).click();
  await expect(page.getByTestId("run-card")).toBeVisible();
});

test("two runs in parallel stay independent", async ({ page }) => {
  await sendSuggestion(page, "Check my inbox and today's calendar");
  const panel = page.locator("#run-panel");
  await panel.getByRole("button", { name: "Run plan" }).click();
  const first = page.url();

  await page.getByRole("button", { name: "New chat" }).click();
  await send(page, "What's the weather in Tokyo?");
  await panel.getByRole("button", { name: "Run plan" }).click();
  await panel.getByRole("button", { name: "Cancel run" }).click();
  await expect(panel.getByText("Cancelled", { exact: true }).first()).toBeVisible();

  await page.goto(first);
  await expect(panel.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 10_000 });
});

test("the browser only talks to the local frontend and backend", async ({ page }) => {
  const hosts = new Set<string>();
  page.on("request", (request) => hosts.add(new URL(request.url()).host));

  await sendSuggestion(page, BRIEFING);
  const panel = page.locator("#run-panel");
  await panel.getByRole("button", { name: "Run plan" }).click();
  await panel.getByRole("button", { name: "Approve and send" }).click({ timeout: 10_000 });
  await expect(task(panel, "t5")).toHaveAttribute("data-status", "completed");

  expect([...hosts].sort()).toEqual(["localhost:3201", "localhost:8100"]);
});

test("the sidebar shows when the backend goes away and comes back", async ({ page }) => {
  await page.goto("/");
  const status = page.getByRole("navigation", { name: "Conversations" }).getByRole("status");
  await expect(status).toHaveText("Backend connected, tools mocked");

  // Cut the browser off from the API (as if the server were stopped).
  await page.route("http://localhost:8100/**", (route) => route.abort("connectionrefused"));
  await page.getByLabel("Message", { exact: true }).fill("What's the weather in Paris?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(status).toHaveText("Can't reach the backend. Retrying…");

  await page.unroute("http://localhost:8100/**");
  await expect(status).toHaveText("Backend connected, tools mocked", { timeout: 10_000 });
});
