# Frontend: Personal Assistant (mock mode)

Next.js 16 + TypeScript + Tailwind CSS 4. Everything runs in the browser against an in-memory **mock API**. No LLM calls, no external services, and nothing is ever sent anywhere.

![Desktop: run in progress](docs/screenshots/desktop-3-running.png)

## Run it

Requires Node 20.9 or newer.

```bash
cd frontend
npm install
npm run dev            # http://localhost:3000
```

| Command | What it does |
| --- | --- |
| `npm test` | Unit tests (Vitest): engine, graph, planner, mock client, metrics |
| `npm run test:e2e` | Browser tests (Playwright, desktop + Pixel 7) against a production build. First run: `npx playwright install chromium` |
| `npm run build` | Production build |
| `npm run typecheck` / `npm run lint` | Static checks |

### Try these
- **"Give me a morning briefing and send it to Telegram"**: three tasks in parallel, a summary, then an approval request.
- **"…and simulate failure"**: the first task fails and its dependants are skipped.
- **"simulate error"**: the chat request fails (503), with a retry option.
- Append `?mock_speed=3` to the URL to slow every task down 3×.

## Architecture

```
src/
  lib/api/types.ts        API contract (snake_case, same JSON FastAPI will send)
  lib/api/client.ts       ApiClient interface: the only thing the UI calls
  lib/api/index.ts        createApiClient(): picks mock vs real backend
  lib/api/mock/           MOCK ONLY: planner, engine, tool outputs, seed data
  lib/workflow/           pure logic shared by mock + real: reducer, graph, metrics
  lib/state/              app state reducer (no effects)
  hooks/use-assistant.ts  effects: loading, sending, one event stream per live run
  components/             rendering only; no imports from lib/api/mock
```

**Events are the source of truth.** The engine never edits a run directly. It emits a `WorkflowEvent`, and `applyEvent()` (`lib/workflow/reducer.ts`) produces the new state. The UI runs the same reducer on the streamed events, so the panel always shows exactly what the backend says happened. FastAPI's SSE stream will feed the same function.

## Mock API contract

| Method | Route | Body / returns |
| --- | --- | --- |
| GET | `/api/conversations` | `Conversation[]` |
| GET | `/api/conversations/{id}/messages` | `ChatMessage[]` |
| POST | `/api/chat` | `{conversation_id, message}` → `{conversation, user_message, assistant_message, run}`. `run` starts as `planned` |
| GET | `/api/runs/{id}` | `WorkflowRun` (includes `last_event_seq`) |
| POST | `/api/runs/{id}/start` | `WorkflowRun` (409 if already started) |
| POST | `/api/runs/{id}/cancel` | `WorkflowRun` (409 if finished) |
| POST | `/api/approvals/{id}` | `{decision: "approve" \| "reject"}` → `ApprovalRequest` (409 if resolved) |
| GET | `/api/stats` | `UsageStats` |
| GET | `/api/runs/{id}/events` | SSE stream of `WorkflowEvent`, `id:` = `seq`, resumable with `Last-Event-ID` |

Event types: `run.started`, `task.started`, `task.completed`, `task.failed`, `task.skipped`, `task.cancelled`, `approval.requested`, `approval.resolved`, `run.completed`, `run.failed`, `run.cancelled`. Full shapes are in [`src/lib/api/types.ts`](src/lib/api/types.ts).

**Execution rules the backend must keep:**
- A task starts when all its dependencies have completed.
- If a dependency fails, is skipped or is cancelled, its dependants are skipped.
- `requires_approval` tasks pause in `waiting_for_approval`. Approving runs the task; rejecting skips it.
- Cancelling expires open approvals and cancels every unfinished task.
- A run fails if any task failed; otherwise it completes, even if an approval was rejected.

## Connecting FastAPI

1. Write `HttpApiClient implements ApiClient` with `fetch` for the REST routes. Map `{"detail": ...}` errors to `ApiError(status, message)`.
2. Implement `subscribeToRun` with `EventSource(`${API}/api/runs/${id}/events`)`. Pass `afterSeq` as `Last-Event-ID` (or `?after_seq=`), `JSON.parse` each message, and return `() => source.close()`.
3. Return it from `createApiClient()` when `NEXT_PUBLIC_API_URL` is set.
4. Port the execution rules above to the backend (LangGraph + the DAG scheduler), emitting the same events.
5. Delete `lib/api/mock/` once you no longer need it for demos. Nothing in `components/`, `hooks/` or `lib/workflow/` changes.

The FastAPI app will also need CORS for the frontend origin. The approval endpoint must be the only path that can trigger side-effecting tools.

## Screenshots

| | |
| --- | --- |
| ![Proposed plan](docs/screenshots/desktop-2-plan.png) | ![Approval](docs/screenshots/desktop-4-approval.png) |
| ![Completed, dark](docs/screenshots/desktop-6-dark.png) | ![Failed run](docs/screenshots/desktop-7-failed-dark.png) |

Mobile: [chat](docs/screenshots/mobile-2-chat-approval.png) · [run sheet](docs/screenshots/mobile-3-sheet-approval.png) · [drawer](docs/screenshots/mobile-4-drawer.png)
