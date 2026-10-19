import { expect, test } from "@playwright/test";

import { send, sendSuggestion, statuses, task, timings } from "./helpers";

const BRIEFING = "Give me a morning briefing and send it to Telegram";

test("shows the plan, runs independent tasks together, and completes after approval", async ({ page }) => {
  await sendSuggestion(page, BRIEFING);
  const panel = page.locator("#run-panel");

  // Plan is proposed, nothing runs yet.
  await expect(panel.getByRole("heading", { name: "Proposed plan" })).toBeVisible();
  await expect(panel.getByText("3 run in parallel")).toBeVisible();
  for (const id of ["t1", "t2", "t3", "t4", "t5"]) await expect(task(panel, id)).toHaveAttribute("data-status", "pending");
  await expect(task(panel, "t4")).toContainText("Waits for Check Singapore weather, Read today's calendar and Scan unread email");

  await panel.getByRole("button", { name: "Run plan" }).click();

  // Telegram needs approval, with a preview of the exact message.
  await expect(task(panel, "t5")).toHaveAttribute("data-status", "waiting_for_approval", { timeout: 10_000 });

  // Checked from the rendered timeline, not by catching a moment: deterministic under any load.
  // Step 1 tasks all started together; the summary started only after the last of them finished.
  const [weather, calendar, email, summary] = await timings(panel, ["t1", "t2", "t3", "t4"]);
  // Each start event carries its own timestamp, so allow a few ms of clock jitter.
  for (const t of [weather, calendar, email]) expect(t.start).toBeLessThan(50);
  expect(summary.start).toBeGreaterThanOrEqual(Math.max(weather.end, calendar.end, email.end));
  const approval = panel.getByRole("region", { name: "Send this to Telegram?" });
  await expect(approval).toContainText(/Singapore: \d+°C/);
  await expect(page.getByTestId("run-card")).toContainText("Needs your approval");

  await approval.getByRole("button", { name: "Approve and send" }).click();
  await expect(task(panel, "t5")).toHaveAttribute("data-status", "completed", { timeout: 10_000 });
  await expect(panel.getByText("Completed", { exact: true }).first()).toBeVisible();
  await expect(panel.getByRole("region", { name: "Summary" })).toContainText("nothing was actually sent");
  await expect(page.getByTestId("run-card")).toContainText("5 of 5 steps");
});

test("rejecting the approval skips sending but completes the run", async ({ page }) => {
  await sendSuggestion(page, BRIEFING);
  const panel = page.locator("#run-panel");
  await panel.getByRole("button", { name: "Run plan" }).click();

  await panel.getByRole("button", { name: "Reject" }).click();
  await expect(task(panel, "t5")).toHaveAttribute("data-status", "skipped");
  await expect(panel.getByRole("region", { name: "Summary" })).toContainText("you rejected the message");
});

test("cancelling stops running and pending tasks", async ({ page }) => {
  await sendSuggestion(page, "Check my inbox and today's calendar", { slow: true });
  const panel = page.locator("#run-panel");
  await panel.getByRole("button", { name: "Run plan" }).click();
  // Cancel as soon as the run is live (the whole run takes ~3s at demo speed).
  await panel.getByRole("button", { name: "Cancel run" }).click();

  await expect(panel.getByText("Cancelled", { exact: true }).first()).toBeVisible();
  // A task that finished before the cancel landed stays completed; nothing is left running or pending.
  const [calendar, email, summary] = await statuses(panel, ["t1", "t2", "t3"]);
  expect(["completed", "cancelled"]).toContain(calendar);
  expect(["completed", "cancelled"]).toContain(email);
  expect(summary).toBe("cancelled");
  await expect(panel.getByRole("button", { name: "Cancel run" })).toHaveCount(0);
});

test("a failed task skips its dependants and fails the run", async ({ page }) => {
  await sendSuggestion(page, "Check the weather in Oslo and simulate failure");
  const panel = page.locator("#run-panel");
  await panel.getByRole("button", { name: "Run plan" }).click();

  await expect(task(panel, "t1")).toHaveAttribute("data-status", "failed");
  await expect(task(panel, "t2")).toHaveAttribute("data-status", "skipped");
  await expect(panel.getByText("The run stopped")).toBeVisible();
});

test("shows an error with retry when the assistant is unavailable", async ({ page }) => {
  await page.goto("/");
  await send(page, "simulate error");
  const alert = page.getByRole("alert").filter({ hasText: "Message not sent" });
  await expect(alert).toContainText("unavailable");
  await expect(alert.getByRole("button", { name: "Send again" })).toBeVisible();
});

test("loads seeded history (demo mode only)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name.endsWith("-http"), "The backend starts without demo data.");
  await page.goto("/");
  await page.getByRole("button", { name: /What's the weather in Tokyo/ }).click();
  await expect(page.getByTestId("run-card")).toContainText("Completed");
});

test("switches theme and remembers it", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

test("integrations show their real status from the backend", async ({ page }) => {
  await page.goto("/");
  const weather = page.getByTestId("integration-get_weather");
  await expect(weather).toContainText("Simulated");
  await expect(page.getByTestId("integration-telegram_send_message")).toContainText("asks first");
});
