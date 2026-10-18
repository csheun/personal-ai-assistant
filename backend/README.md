# Backend

FastAPI service that turns a chat message into a validated plan, runs it as a dependency graph with live progress over Server-Sent Events, and asks for approval before anything acts on the outside world.

It has two modes, chosen with `MOCK_MODE`:

| | `MOCK_MODE=true` (default) | `MOCK_MODE=false` |
|---|---|---|
| Planner | Keyword rules (`workflows/planner.py`) | LLM via LangChain + LangGraph (`workflows/llm_planner.py`) |
| Tools | 7 simulated tools | Open-Meteo weather, Tavily search, LLM summary, Telegram (real if configured) |
| Keys needed | None | LLM key; `WEB_SEARCH_API_KEY` for search; Telegram token and chat id to really send |

Everything after planning (validation, the executor, approvals, SSE, the API) is the same code in both modes.

## Run

Requires Python 3.11+ (developed on 3.13).

```bash
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # add ,openai or ,anthropic for those providers
cp .env.example .env             # MOCK_MODE=true works with no keys
uvicorn app.main:app --reload    # http://localhost:8000/docs
```

Run as **one worker process** (see [Limitations](#limitations)).

## How a request flows

```
POST /api/chat
  └─ WorkflowService.send_message
       └─ Planner.plan(message, today)
            mock: keyword rules
            live: LLMPlanner (LangGraph)  draft ─▶ validate ─▶ repair (at most once) ─▶ validate
                    └─ validation.py: tools, arguments, ids, dependencies, cycles, size, shape, risk
       ├─ direct answer → assistant message, no run
       └─ valid plan    → WorkflowRun(status="planned") + WorkflowRunner
POST /api/workflows/{id}/start
  └─ WorkflowRunner (asyncio): every task whose dependencies completed starts now
       └─ bindings.resolve_arguments (fills summary sources / Telegram text from upstream results)
       └─ ToolRegistry.execute: validate input → handler (timeout) → validate output
       └─ every change: event → apply_event (reducer) → EventLog → SSE subscribers
  external_write task (Telegram) → approval.requested (arguments frozen)
POST /api/workflows/{id}/approve  → runner re-checks the approval → runs the frozen arguments once
```

## API

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/chat` | `{conversation_id?, message}` → conversation, both messages, and a `run` in status `planned` (or `null` for a direct answer). 502 if no valid plan, 503 if the LLM is unavailable |
| GET | `/api/conversations`, `/api/conversations/{id}/messages` | History |
| GET | `/api/workflows/{id}` | Run snapshot, with `last_event_id` and `planning` metadata |
| POST | `/api/workflows/{id}/start` | Start a planned run |
| POST | `/api/workflows/{id}/approve` | `{approval_id, decision: "approve" \| "reject"}` |
| POST | `/api/workflows/{id}/cancel` | Cancel a planned or live run |
| GET | `/api/workflows/{id}/events` | SSE stream (below) |
| GET | `/api/capabilities` | Mode, model and available tools (never secrets) |
| GET | `/api/stats` | Run, tool, approval and LLM token totals |
| GET | `/health` | Liveness |

Errors are `{"detail": "..."}`: 404 unknown id, 409 wrong state (such as approving twice), 422 invalid input, 502 planning failed, 503 LLM unavailable.

### Events

Every state change is one envelope: `{id, run_id, timestamp, type, task_id, data}`. Types are `run.started`, `task.started`, `task.completed`, `task.failed`, `task.skipped`, `task.cancelled`, `approval.requested`, `approval.resolved`, `run.completed`, `run.failed` and `run.cancelled`.

- `id` increases per run and is also the SSE `id:`. Resume with `?after=<id>` or `Last-Event-ID` (the header wins).
- The stream replays missed events, sends live ones and keep-alives, and closes after the run's last event. Disconnecting never affects the run.
- `contracts/workflow-scenarios.json` is recorded from this runner, and the frontend replays it through its TypeScript reducer, so both sides agree on every state.

## Code map

```
app/
  main.py               wiring by MOCK_MODE, one pooled httpx client, CORS, error → HTTP mapping
  config.py             every setting (env / .env); secrets are SecretStr
  llm/
    provider.py         the only module that knows the provider (groq / openai / anthropic)
    client.py           LLMClient: timeouts, usage metadata, LLMUnavailable vs LLMOutputError
  providers/            HTTP clients only: open_meteo.py, tavily.py, telegram.py (+ typed ProviderError)
  tools/
    base.py             Tool + ToolRegistry: allow-list, validation, per-tool timeouts, risk, bound inputs
    weather.py, web_search.py, summarize.py, telegram.py   mock + real implementations, same names
    live.py             the live registry (registers only configured tools)
  workflows/
    models.py           the API contract (Pydantic) = frontend/src/lib/api/types.ts
    plan_schema.py      what the LLM must return
    validation.py       the rules a plan must pass before anything runs
    llm_planner.py      LangGraph draft/validate/repair loop
    planner.py          mock keyword planner
    plans.py            Plan / DirectReply / Planner interface
    bindings.py         how tasks consume upstream results
    runner.py           the executor (one per run)
    reducer.py          apply_event: the only way run state changes
    events.py           per-run event log: replay + live fan-out + heartbeats
    service.py          in-memory store; what the routes call
```

## How LangGraph, the planner, the executor and the registry fit together

- **The tool registry** is the source of truth for what can run. Each tool declares its typed input and output, a risk level (`read` or `external_write`), its timeout, and which inputs the backend fills from upstream results. The planner prompt, the validator and the runner all read the registry, so adding a tool in one place updates all three.
- **The planner (LangGraph)** only proposes. Its graph is `draft → validate → repair → validate`, with a hard attempt limit. LangGraph fits here because this is a small stateful loop with a conditional exit. Its output is plain data: a list of `WorkflowTask`.
- **The validator** decides. Plans that use unknown tools, take invalid arguments, reference missing dependencies, contain cycles, are too big or too deep, or have the wrong shape never run. Approval requirements come from tool risk levels, never from the LLM.
- **The executor (`WorkflowRunner`)** runs. It's plain asyncio, the same code as in mock mode. Independent tasks run concurrently, failures skip dependants, cancellation cancels in-flight HTTP calls, and side effects need an approved approval that the runner checks at the moment of execution.

LangGraph is deliberately **not** the executor. A second engine would mean two sources of workflow state, and approvals, SSE and cancellation would all have to be rebuilt.

## Safety properties (each covered by tests)

- The LLM never executes anything: it returns JSON, and Python decides what runs.
- Tools come from an allow-list, and arguments are validated twice (when planning and when executing).
- The LLM can't choose the Telegram recipient (`TELEGRAM_CHAT_ID` only), and can't write a message the summary didn't produce.
- What you approve is exactly what's sent. A second approve gets 409, and no send is retried automatically.
- A timeout or dropped connection after sending reports `delivery_unknown`, never "not sent".
- Fetched content goes to the LLM fenced as untrusted data. Citations are limited to URLs that really came from the search.
- Secrets stay on the server. Provider errors are mapped to safe messages, and the httpx request log is silenced because Telegram's URL contains the token.

## Tests

```bash
pytest                       # 153 tests, no network (an autouse fixture blocks sockets)
LIVE_TESTS=1 pytest -m live  # optional: real Open-Meteo, Tavily and LLM (see tests/live/README.md)
```

The live-mode API tests (`tests/test_live_mode.py`) run the whole stack through HTTP, using a scripted LLM and `httpx.MockTransport` for the providers.

## Limitations

- **Memory only:** a restart loses conversations, runs and pending approvals.
- **Single worker:** with `uvicorn --workers N`, a stream or approval can reach a process that doesn't own the run. Moving state to PostgreSQL (plus a pub/sub for events) is the planned fix.
- **"Today" is the server's local date,** used to resolve "tomorrow" and weekdays. A hosted version should take the user's time zone from the browser.
- **No authentication or rate limiting yet.** CORS is the only restriction.
- **Free LLM tiers rate-limit quickly** (about 8k tokens/minute on Groq); a full run uses about 3.5k.
- **Plans have a fixed shape:** data steps, then one summary, then an optional send. That keeps validation simple; chained data steps (search → search) would need more binding rules.
