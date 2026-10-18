# Backend

FastAPI service that plans and runs the assistant's workflows and streams their progress to the frontend over Server-Sent Events.

> **Milestone 3: everything is mocked.** The planner uses keyword rules. All seven tools return simulated data (`"mocked": true`), and nothing calls an LLM or an external API. The test suite fails if any code opens a network connection.

## Run

Requires Python 3.11+ (developed on 3.13).

```bash
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # optional: the defaults work
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs. Tests: `pytest`.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/chat` | `{conversation_id?, message}` → conversation, both messages, and a `run` in status `planned` (or `null` for a direct reply) |
| GET | `/api/conversations` · `/api/conversations/{id}/messages` | History for the sidebar |
| GET | `/api/workflows/{id}` | Run snapshot, with `last_event_id` |
| POST | `/api/workflows/{id}/start` | Begin executing a planned run |
| POST | `/api/workflows/{id}/approve` | `{approval_id, decision: "approve" \| "reject"}` |
| POST | `/api/workflows/{id}/cancel` | Cancel a planned or live run |
| GET | `/api/workflows/{id}/events` | SSE stream, resumable (see below) |
| GET | `/api/stats` | Totals across runs |

Errors are `{"detail": ...}`: 404 for an unknown id, 409 for an action that doesn't fit the run's state (such as approving twice), 422 for invalid input, and 503 when the assistant is unavailable (send "simulate error" to trigger it).

### Events

Every state change is an event with one envelope:

```json
{ "id": 7, "run_id": "run_…", "timestamp": "…Z", "type": "task.completed", "task_id": "t2",
  "data": { "result": { "tool_name": "…", "ok": true, "output": {…}, "mocked": true }, "duration_ms": 1301 } }
```

Event types: `run.started`, `task.started`, `task.completed`, `task.failed`, `task.skipped`, `task.cancelled`, `approval.requested`, `approval.resolved`, `run.completed`, `run.failed`, `run.cancelled`.

- **`id` increases per run** and doubles as the SSE `id:`. A run snapshot's `last_event_id` says which events it already reflects.
- **Resume** with `?after=<id>` or the browser's automatic `Last-Event-ID` header. The header wins, because it's newer.
- **The stream** replays missed events, sends live ones, sends keep-alive comments when idle, and closes after the run's final event. Completed runs remain available through `GET /api/workflows/{id}` and a replay of their stream.
- **Disconnecting** only ends that stream; the run keeps going.

## Layout

```
app/
  main.py                create_app(): wiring, CORS, domain-error → HTTP mapping
  config.py              settings from env / .env
  api/routes/            thin HTTP layer: chat, conversations (+stats), workflows (+SSE)
  workflows/
    models.py            the API contract (Pydantic); mirrors frontend/src/lib/api/types.ts
    reducer.py           apply_event(run, event): the only way run state changes
    graph.py             DAG validation, ready/blocked tasks, parallel-time saving
    planner.py           MOCK keyword planner → Plan (fixed task graph)
    bindings.py          feeds upstream results into the summary and Telegram arguments
    runner.py            asyncio executor for one run (concurrency, approval, cancel, failure)
    events.py            per-run event log: replay + live fan-out + heartbeats
    service.py           in-memory store; owns runners; what routes call
    errors.py            NotFound / WorkflowConflict / AssistantUnavailable
  tools/                 registry (validation, timeouts, side-effect flag) + 7 mocked tools
  agent/, llm/           Milestone 1 LangGraph agent, kept for Milestone 4, not routed
```

**How a run executes.** `start()` emits `run.started` and starts every task whose dependencies have completed, each in its own `asyncio` task. When one finishes, the runner emits its result and re-evaluates the graph. When a dependency fails, its dependants are skipped. Tools flagged `side_effects` (Telegram) always get `requires_approval`, and they wait for `POST /approve`. The runner never edits state directly: it creates an event, applies it with `apply_event`, and appends it to the log. That makes the snapshot and the stream two views of the same data.

**Contract tests.** `tests/contract_scenarios.py` records approve, reject, cancel and failure runs into `contracts/workflow-scenarios.json`. The backend test checks the runner still produces exactly that file, and the frontend test replays it through the TypeScript reducer. After an intentional contract change, run `python -m tests.contract_scenarios --write`.

## What Milestone 4 replaces

| Module | Change |
| --- | --- |
| `workflows/planner.py` | Swap `MockPlanner` for an LLM planner (the `app/agent` LangGraph code) that returns the same `Plan`. Validate the generated DAG with `graph.validate_dag`. |
| `tools/weather.py`, `web_search.py`, `telegram.py` | Replace each handler with a real API call. Input and output models stay the same, and so does the `side_effects` flag on Telegram. |
| `tools/summarize.py` | Generate the summary text with the LLM instead of templates. |
| `tools/__init__.py` | Stop wrapping real tools in `with_latency`, and register API clients with secrets from settings. |
| `workflows/bindings.py` | Extend if the LLM planner needs more than "summary ← sources" and "Telegram ← summary". |
| `runner.py`, `events.py`, routes, `models.py`, `reducer.py` | Unchanged. |

Later milestones replace the dicts in `service.py` with a PostgreSQL repository.
