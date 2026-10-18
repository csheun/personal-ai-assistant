import { expect, test } from "@playwright/test";

import { sendSuggestion, task } from "./helpers";

test("single-column chat with drawer and run sheet", async ({ page }) => {
  await page.goto("/");

  // Desktop columns are hidden; nothing overflows horizontally.
  await expect(page.locator("#run-panel")).toBeHidden();
  await expect(page.getByRole("button", { name: "New chat" })).toBeHidden();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  // Sidebar opens as a drawer.
  await page.getByRole("button", { name: "Open conversations" }).click();
  const drawer = page.getByRole("dialog", { name: "Conversations" });
  await expect(drawer.getByRole("button", { name: "New chat" })).toBeVisible();
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(drawer).toBeHidden();

  // Workflow details open as a bottom sheet from the chat.
  await sendSuggestion(page, "Give me a morning briefing and send it to Telegram");
  await page.getByRole("button", { name: "View plan" }).click();
  const sheet = page.getByRole("dialog", { name: "Workflow run" });
  await expect(sheet.getByRole("heading", { name: "Proposed plan" })).toBeVisible();

  await sheet.getByRole("button", { name: "Run plan" }).click();
  await sheet.getByRole("button", { name: "Approve and send" }).click();
  await expect(task(sheet, "t5")).toHaveAttribute("data-status", "completed");

  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(page.getByTestId("run-card")).toContainText("Completed");
});
