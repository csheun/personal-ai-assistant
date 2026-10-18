import { expect, type Page } from "@playwright/test";

/** `slow` stretches simulated task durations 3x so "running" states are reliably observable. */
export async function sendSuggestion(page: Page, text: string, { slow = false } = {}) {
  await page.goto(slow ? "/?mock_speed=3" : "/");
  // Scoped to <main>: the same text can also be a conversation title in the sidebar.
  await page.getByRole("main").getByRole("button", { name: text }).click();
  await expect(page.getByTestId("run-card")).toBeVisible();
}

export async function send(page: Page, text: string) {
  await page.getByLabel("Message", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message" }).click();
}

export const task = (scope: Page | ReturnType<Page["locator"]>, id: string) => scope.getByTestId(`task-${id}`);

/** Reads several task statuses in one snapshot, so "running at the same time" is checked atomically. */
export function statuses(scope: ReturnType<Page["locator"]>, ids: string[]) {
  return scope.evaluate(
    (root, ids) => ids.map((id) => root.querySelector(`[data-testid="task-${id}"]`)?.getAttribute("data-status")),
    ids,
  );
}

/** Start/finish offsets (ms from run start) as rendered on the timeline. */
export function timings(scope: ReturnType<Page["locator"]>, ids: string[]) {
  return scope.evaluate(
    (root, ids) =>
      ids.map((id) => {
        const row = root.querySelector(`[data-testid="task-${id}"]`) as HTMLElement | null;
        return { start: Number(row?.dataset.startedMs), end: Number(row?.dataset.finishedMs) };
      }),
    ids,
  );
}
