const DEMO_SUGGESTIONS = [
  "Give me a morning briefing and send it to Telegram",
  "What's the weather in Paris and the latest news on the Louvre?",
  "Check my inbox and today's calendar",
  "Check the weather in Oslo and simulate failure",
];

// Requests the live planner and tools can actually serve (weather, web search, Telegram, no-tool answers).
const LIVE_SUGGESTIONS = [
  "Check tomorrow's weather in Singapore, search for recent AI news, summarize both, and send the summary to Telegram.",
  "Will it rain in London this Saturday?",
  "What's the latest news about the James Webb telescope?",
  "In one sentence, what's the difference between a process and a thread?",
];

export function EmptyState({ onPick, disabled, live }: { onPick: (text: string) => void; disabled: boolean; live: boolean }) {
  const SUGGESTIONS = live ? LIVE_SUGGESTIONS : DEMO_SUGGESTIONS;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-1 py-10">
      <h1 className="text-[28px] font-semibold leading-tight tracking-tight sm:text-[34px]">What should I take care of?</h1>
      <p className="mt-2 max-w-[56ch] text-muted">
        I plan the steps first, run independent ones at the same time, and ask before sending anything on your behalf.
      </p>
      <ul className="mt-8 grid gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((text) => (
          <li key={text}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(text)}
              className="h-full w-full rounded-xl bg-surface px-4 py-3 text-left text-sm ring-1 ring-line transition-colors hover:ring-line-strong disabled:opacity-50"
            >
              {text}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
