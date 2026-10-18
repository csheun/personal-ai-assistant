# Backend — Milestone 1

FastAPI + LangGraph backend for the Personal AI Assistant. In this milestone an LLM decides which tools to call, Python validates and runs them, and the LLM writes the final answer.

> **Both tools (`get_weather`, `web_search`) are MOCKED.** They return fake data, flagged `"mocked": true` in every result.

## Layout

```
app/
  main.py            create_app() factory; builds the agent once at startup
  config.py          all env vars (pydantic-settings); secrets are SecretStr
  api/               HTTP layer only: routes, request/response schemas, DI
  agent/graph.py     LangGraph StateGraph: llm <-> tools loop
  agent/service.py   AgentService: the only thing routes call; maps errors
  llm/provider.py    LLM_PROVIDER -> LangChain chat model
  tools/base.py      Tool + ToolRegistry (allow-list, validation, timeout)
  tools/*.py         individual tools (currently mocked)
tests/               offline tests using a scripted fake LLM
```

## Setup

Requires Python 3.11+ (developed on 3.13).

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # add ,openai or ,anthropic for those providers
cp .env.example .env             # then set LLM_API_KEY
```

## Run

```bash
uvicorn app.main:app --reload
```

The server fails at startup if the LLM is misconfigured (for example, a missing key). Interactive docs are at http://localhost:8000/docs.

## Try it

```bash
curl localhost:8000/health

curl -X POST localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the weather in Singapore?"}'
```

If `tool_calls` in the response contains a `get_weather` entry with `"ok": true`, the LLM chose a tool and Python ran it. `iterations` counts LLM calls. One tool round trip gives at least 2.

## Test

```bash
pytest
```

The tests never call a real LLM. `tests/fakes.py` provides `ScriptedChatModel`, which returns pre-written responses (including tool calls) so the graph, registry and API can be tested quickly and deterministically.

## Adding a tool

1. Create `app/tools/my_tool.py` with a `ToolInput` subclass, an output `BaseModel`, an `async` handler and a `Tool(...)`.
2. Register it in `build_default_registry()` in `app/tools/__init__.py`.

The LLM sees it automatically: the JSON schema is generated from the input model, so the `Field(description=...)` text is effectively prompt text.
