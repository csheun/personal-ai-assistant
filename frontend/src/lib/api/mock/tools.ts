/**
 * MOCKED tool behaviour. Produces believable, deterministic outputs and durations.
 * Nothing here talks to a real service; every result is flagged `mocked: true`.
 */
import type { ToolName, ToolResult, WorkflowTask } from "@/lib/api/types";

/** Base simulated latency per tool, before the speed multiplier. */
export const TOOL_DURATION_MS: Record<ToolName, number> = {
  get_weather: 900,
  calendar_list_events: 1300,
  gmail_search: 1700,
  web_search: 2100,
  document_search: 1500,
  summarize: 1200,
  telegram_send_message: 700,
};

const FAILURE_MESSAGES: Record<ToolName, string> = {
  get_weather: "The weather service didn't respond in time.",
  calendar_list_events: "Google Calendar returned an authorization error.",
  gmail_search: "Gmail rate-limited the request.",
  web_search: "The search provider returned an error.",
  document_search: "The document index is unavailable.",
  summarize: "The language model request failed.",
  telegram_send_message: "Telegram rejected the message.",
};

export function simulateToolResult(task: WorkflowTask, upstream: WorkflowTask[], fail: boolean): ToolResult {
  if (fail) {
    return {
      tool_name: task.tool_name,
      ok: false,
      output: null,
      error: { code: "simulated_failure", message: FAILURE_MESSAGES[task.tool_name] },
      mocked: true,
    };
  }
  return { tool_name: task.tool_name, ok: true, output: mockOutput(task, upstream), error: null, mocked: true };
}

function mockOutput(task: WorkflowTask, upstream: WorkflowTask[]): Record<string, unknown> {
  const args = task.arguments;
  switch (task.tool_name) {
    case "get_weather":
      return { city: args.city, temperature_c: 31, high_c: 33, low_c: 26, condition: "Partly cloudy, showers after 4 pm" };
    case "calendar_list_events":
      return {
        date: args.date,
        events: [
          { time: "09:30", title: "Team standup" },
          { time: "13:00", title: "Lunch with Priya" },
          { time: "16:00", title: "Design review" },
        ],
      };
    case "gmail_search":
      return {
        query: args.query,
        messages: [
          { from: "DBS Bank", subject: "Your statement is ready", received: "07:12" },
          { from: "Priya", subject: "Lunch — still on?", received: "08:03" },
        ],
      };
    case "web_search":
      return {
        query: args.query,
        results: [
          { title: `Latest on ${args.query}`, url: "https://example.com/mock/1", snippet: "Simulated search result." },
          { title: `${args.query}: what changed this week`, url: "https://example.com/mock/2", snippet: "Simulated search result." },
        ],
      };
    case "document_search":
      return {
        query: args.query,
        passages: [{ document: "Notes/Q4 goals.md", excerpt: "Ship the assistant MVP before December." }],
      };
    case "summarize":
      return { text: summarizeUpstream(upstream) };
    case "telegram_send_message":
      // Mock mode never sends anything. `delivered: false` makes that explicit in the result.
      return { chat: args.chat, delivered: false, note: "Mock mode: no message was sent to Telegram." };
  }
}

/** Loose view of the mock outputs above, for reading them back when summarizing. */
interface MockOutput {
  city: string;
  temperature_c: number;
  condition: string;
  events: { time: string; title: string }[];
  messages: { from: string; subject: string }[];
  results: unknown[];
  query: string;
  passages: { excerpt: string }[];
}

function summarizeUpstream(upstream: WorkflowTask[]): string {
  const lines: string[] = [];
  for (const task of upstream) {
    const out = task.result?.output as MockOutput | null | undefined;
    if (!out) continue;
    switch (task.tool_name) {
      case "get_weather":
        lines.push(`${out.city}: ${out.temperature_c}°C, ${String(out.condition).toLowerCase()}.`);
        break;
      case "calendar_list_events":
        lines.push(`${out.events.length} events today, starting with ${out.events[0].title} at ${out.events[0].time}.`);
        break;
      case "gmail_search":
        lines.push(`${out.messages.length} new emails, including "${out.messages[1].subject}" from ${out.messages[1].from}.`);
        break;
      case "web_search":
        lines.push(`Found ${out.results.length} recent articles about ${out.query}.`);
        break;
      case "document_search":
        lines.push(`From your notes: "${out.passages[0].excerpt}"`);
        break;
    }
  }
  return lines.length ? lines.join(" ") : "Nothing to summarize.";
}
