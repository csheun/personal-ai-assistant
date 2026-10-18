import { defineConfig, devices } from "@playwright/test";

const PORT = 3200;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", testIgnore: /mobile\.spec/, use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", testMatch: /mobile\.spec/, use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    // Production build at real mock speed: tasks must run long enough for in-flight states to be observable.
    command: `npm run build && npx next start --port ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
