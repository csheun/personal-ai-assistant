import { defineConfig, devices } from "@playwright/test";

/**
 * Runs the same UI tests against both client modes:
 * - *-mock: frontend build with the in-browser mock (port 3200)
 * - *-http: frontend build talking to a real FastAPI server (ports 3201 → 8100)
 * Plus HTTP-only tests in http.spec.ts. Production builds; mock tools run at demo speed.
 */
const MOCK = 3200;
const HTTP = 3201;
const API = 8100;

const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } };
const build = (dir: string, port: number) =>
  `NEXT_DIST_DIR=${dir} npm run build && NEXT_DIST_DIR=${dir} npx next start --port ${port}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { trace: "retain-on-failure" },
  projects: [
    { name: "desktop-mock", testMatch: /workflow\.spec/, use: { ...desktop, baseURL: `http://localhost:${MOCK}` } },
    { name: "mobile-mock", testMatch: /mobile\.spec/, use: { ...devices["Pixel 7"], baseURL: `http://localhost:${MOCK}` } },
    { name: "desktop-http", testMatch: /(workflow|http)\.spec/, use: { ...desktop, baseURL: `http://localhost:${HTTP}` } },
    { name: "mobile-http", testMatch: /mobile\.spec/, use: { ...devices["Pixel 7"], baseURL: `http://localhost:${HTTP}` } },
  ],
  webServer: [
    {
      command: `../backend/.venv/bin/uvicorn app.main:app --app-dir ../backend --port ${API}`,
      env: { MOCK_LATENCY_SCALE: "1", CORS_ORIGINS: `["http://localhost:${HTTP}"]` },
      url: `http://localhost:${API}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: build(".next-e2e-mock", MOCK),
      env: { NEXT_PUBLIC_API_MODE: "mock" },
      url: `http://localhost:${MOCK}`,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
    },
    {
      command: build(".next-e2e-http", HTTP),
      env: { NEXT_PUBLIC_API_MODE: "http", NEXT_PUBLIC_API_URL: `http://localhost:${API}` },
      url: `http://localhost:${HTTP}`,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
    },
  ],
});
