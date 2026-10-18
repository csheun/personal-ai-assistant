# Live integration tests (optional)

The normal suite (`pytest`) never touches the network: an autouse fixture blocks
sockets, LLM calls use a scripted fake, and providers use `httpx.MockTransport`.
These tests are the exception. They call the real services and cost real quota.

## Automated

```bash
cd backend && source .venv/bin/activate
LIVE_TESTS=1 pytest -m live -v                    # Open-Meteo, Tavily, LLM planner (read-only)
LIVE_TESTS=1 LIVE_TELEGRAM=1 pytest -m live -v    # + sends ONE real Telegram message
```

Each test reads `backend/.env` and skips itself if its key is missing.

## Manual end-to-end checklist

Set `MOCK_MODE=false` in `backend/.env`, start both apps (see the root README), open
http://localhost:3000 and check the sidebar says **Backend connected, live AI**.

| # | Send | Expect |
|---|------|--------|
| 1 | "Check tomorrow's weather in Singapore, search for recent AI news, summarize both, and send the summary to Telegram." | Plan: weather and search in step 1, summary, Telegram. **Run plan**: steps 1 run together; approval card shows the exact text; **Approve and send**: message arrives (or "simulated" if Telegram isn't configured); summary has source links |
| 2 | "Will it rain in London this Saturday?" | Weather + summary only, with Saturday's date |
| 3 | "In one sentence, what is a DAG?" | Direct answer, no run |
| 4 | "What's the weather tomorrow in Qwxzplorvia?" | Weather fails with "Couldn't find a place…", summary skipped, run failed |
| 5 | Request 1 again, then **Reject** | Telegram skipped, nothing sent, run completed |
| 6 | Refresh the page while waiting for approval | Same run restored; approving still works |
| 7 | Stop the backend | Sidebar: "Can't reach the backend"; recovers when restarted |

Groq's free tier allows about 8,000 tokens per minute; a full run uses about 3,500.
If you see "The AI service is busy (rate limited)", wait a minute.
