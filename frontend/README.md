# Frontend: Personal Assistant

Next.js 16 + TypeScript + Tailwind CSS 4. It has two interchangeable backends:

- **HTTP mode**: the FastAPI server in `../backend` plans and runs the workflows and streams progress over SSE. With the backend's `MOCK_MODE=false`, that means a real LLM planner, live weather and web search, and real Telegram delivery after approval.
- **Demo mode**: everything simulated in the browser, so you need no backend.

The UI asks the backend what it can do (`GET /api/capabilities`). The sidebar shows each integration as **Live**, **Simulated** or **Not connected**, and the approval card says whether approving really sends.

![Desktop: run in progress](docs/screenshots/desktop-3-running.png)

## Run it

Requires Node 20.9 or newer.

```bash
cd frontend
npm install
cp .env.example .env.local     # HTTP mode; start the backend too (see ../backend/README.md)
npm run dev                    # http://localhost:3000
```

For demo mode without a backend, set `NEXT_PUBLIC_API_MODE=mock` in `.env.local` (or delete the file). Restart `npm run dev` after changing it.

| Command | What it does |
| --- | --- |
| `npm test` | Unit tests (Vitest): engine, graph, planner, both clients, state, contract with the backend |
| `npm run test:e2e` | Browser tests (Playwright). Starts FastAPI and two production builds, then runs the UI suite in both modes on desktop and Pixel 7. First run: `npx playwright install chromium` |
| `npm run build` | Production build |
| `npm run typecheck` / `npm run lint` | Static checks |

### Try these
- **"Give me a morning briefing and send it to Telegram"**: three tasks in parallel, a summary, then an approval request.
- **"…and simulate failure"**: the first task fails and its dependants are skipped.
- **"simulate error"**: the chat request fails (503), with a retry option.
- **Refresh mid-run** (HTTP mode): the open conversation is in the URL (`?c=…`), so the run is reloaded from the server and the stream resumes.
- Demo mode only: append `?mock_speed=3` to slow every task down 3×.

## Architecture

```
src/
  lib/api/types.ts        API contract (snake_case JSON); mirrors backend/app/workflows/models.py
  lib/api/client.ts       WorkflowClient interface: the only thing the UI calls
  lib/api/http-client.ts  HttpWorkflowClient: fetch + EventSource against FastAPI
  lib/api/mock/           MockWorkflowClient + in-browser engine, planner, tools, seed data
  lib/api/index.ts        createWorkflowClient(): picks a client from NEXT_PUBLIC_API_MODE
  lib/workflow/           pure logic: reducer (applyEvent), graph, metrics
  lib/state/              app state reducer (no effects)
  hooks/use-assistant.ts  effects: loading, sending, one event stream per live run
  components/             rendering only; never imports from lib/api/mock
```

**Events are the source of truth.** The run panel is the result of applying `WorkflowEvent`s with `applyEvent()`. In HTTP mode the server streams them. In demo mode the in-browser engine produces identical ones. `tests/unit/contract.test.ts` replays streams recorded from the Python runner (`../contracts/workflow-scenarios.json`) and checks the result equals the backend's own snapshot, so the two reducers can't drift apart.

**Streaming and recovery** (HTTP mode):
- The hook opens one SSE stream per unfinished run, starting after the snapshot's `last_event_id`.
- If the connection drops, the panel says "Reconnecting". `EventSource` retries, and the server resumes from `Last-Event-ID`. Duplicate events are dropped by id.
- Snapshots returned by **Run plan** and **Cancel** are applied immediately, so the UI stays correct even while the stream is down.
- If the server is unreachable, requests fail with a clear message, and sending offers "Send again".

## API contract

Routes, event types and execution rules are documented in [`../backend/README.md`](../backend/README.md#api). The TypeScript shapes are in [`src/lib/api/types.ts`](src/lib/api/types.ts).

## Live mode in the UI

Moving to a real LLM and real tools needed no changes to the workflow UI, because it renders the same events. What was added:
- the planning line on each run ("Planned by groq:openai/gpt-oss-120b in 2.7s, 2,587 tokens")
- source links under summaries (only `http(s)` URLs, opened with `noopener noreferrer`)
- LLM call and token statistics
- capability-driven integration statuses and mode-aware text (composer hint, suggestions, approval note)

## Screenshots

| | |
| --- | --- |
| ![Proposed plan](docs/screenshots/desktop-2-plan.png) | ![Approval](docs/screenshots/desktop-4-approval.png) |
| ![Completed, dark](docs/screenshots/desktop-6-dark.png) | ![Failed run](docs/screenshots/desktop-7-failed-dark.png) |

Mobile: [chat](docs/screenshots/mobile-2-chat-approval.png) · [run sheet](docs/screenshots/mobile-3-sheet-approval.png) · [drawer](docs/screenshots/mobile-4-drawer.png)
