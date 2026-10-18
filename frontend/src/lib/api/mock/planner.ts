/**
 * MOCK planner: turns a chat message into a workflow plan with simple keyword
 * rules. In the real app the LLM (LangGraph) produces this plan on the server.
 */
import type { ID, ToolName, WorkflowTask } from "@/lib/api/types";

export interface PlannedTask {
  id: ID;
  title: string;
  tool_name: ToolName;
  arguments: Record<string, unknown>;
  depends_on: ID[];
  requires_approval: boolean;
}

export interface Plan {
  /** Assistant's reply that introduces the plan. */
  reply: string;
  goal: string;
  tasks: PlannedTask[];
  /** Task ids the mock will fail on purpose (triggered by "simulate failure" in the message). */
  failTaskIds: ID[];
}

export type PlannerOutcome =
  | { kind: "plan"; plan: Plan }
  | { kind: "reply"; reply: string }
  /** Triggered by "simulate error": lets you see the chat error state. */
  | { kind: "error"; status: number; message: string };

interface Rule {
  tool: ToolName;
  pattern: RegExp;
  build(message: string): { title: string; arguments: Record<string, unknown> };
}

const RULES: Rule[] = [
  {
    tool: "get_weather",
    pattern: /\b(weather|rain|temperature|forecast|umbrella|briefing)\b/i,
    build: (m) => {
      const city = m.match(/\bin ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)/)?.[1] ?? "Singapore";
      return { title: `Check ${city} weather`, arguments: { city } };
    },
  },
  {
    tool: "calendar_list_events",
    pattern: /\b(calendar|schedule|meetings?|agenda|today|briefing)\b/i,
    build: () => ({ title: "Read today's calendar", arguments: { date: "today" } }),
  },
  {
    tool: "gmail_search",
    pattern: /\b(e-?mails?|gmail|inbox|briefing)\b/i,
    build: () => ({ title: "Scan unread email", arguments: { query: "is:unread newer_than:1d" } }),
  },
  {
    tool: "web_search",
    pattern: /\b(news|search|look up|latest|research)\b/i,
    build: (m) => {
      const topic = m.match(/\b(?:news|search|look up|latest|research)(?: (?:about|on|for))? ([^,.?!]+)/i)?.[1]?.trim();
      const query = topic && topic.length > 2 ? topic : "today's top headlines";
      return { title: `Search the web for ${query}`, arguments: { query } };
    },
  },
  {
    tool: "document_search",
    pattern: /\b(docs?|documents?|notes|files?)\b/i,
    build: () => ({ title: "Search your documents", arguments: { query: "goals and deadlines" } }),
  },
];

const SEND_PATTERN = /\b(telegram|send|message me|notify)\b/i;

export function planFromMessage(message: string): PlannerOutcome {
  if (/simulate error/i.test(message)) {
    return { kind: "error", status: 503, message: "The assistant is unavailable right now. Try again in a moment." };
  }

  const gathered = RULES.filter((r) => r.pattern.test(message));
  const wantsSend = SEND_PATTERN.test(message);

  if (gathered.length === 0) {
    return {
      kind: "reply",
      reply:
        "I can check your weather, calendar, email, the web and your documents, and send the result to Telegram. " +
        'Try "Give me a morning briefing and send it to Telegram."',
    };
  }

  const tasks: PlannedTask[] = gathered.map((rule, i) => ({
    id: `t${i + 1}`,
    tool_name: rule.tool,
    depends_on: [],
    requires_approval: false,
    ...rule.build(message),
  }));

  const summarizeId = `t${tasks.length + 1}`;
  tasks.push({
    id: summarizeId,
    title: "Write a summary",
    tool_name: "summarize",
    arguments: {},
    depends_on: tasks.map((t) => t.id),
    requires_approval: false,
  });

  if (wantsSend) {
    tasks.push({
      id: `t${tasks.length + 1}`,
      title: "Send the summary to Telegram",
      tool_name: "telegram_send_message",
      arguments: { chat: "Me (Saved Messages)" },
      depends_on: [summarizeId],
      requires_approval: true,
    });
  }

  const sources = gathered.map((r) => TOOL_NOUNS[r.tool] ?? r.tool);
  const parallel = sources.length > 1 ? ` at the same time` : "";
  return {
    kind: "plan",
    plan: {
      goal: `Gather ${joinList(sources)}, summarize${wantsSend ? ", then send to Telegram" : ""}.`,
      reply:
        `Here's my plan. I'll check ${joinList(sources)}${parallel}, then summarize what I find` +
        (wantsSend ? ". Before anything goes to Telegram, I'll show you the message and wait for your approval." : ".") +
        " Review the steps and start the run when you're ready.",
      tasks,
      failTaskIds: /simulate failure/i.test(message) ? [tasks[0].id] : [],
    },
  };
}

const TOOL_NOUNS: Partial<Record<ToolName, string>> = {
  get_weather: "the weather",
  calendar_list_events: "your calendar",
  gmail_search: "your inbox",
  web_search: "the web",
  document_search: "your documents",
};

function joinList(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

export function toWorkflowTask(planned: PlannedTask): WorkflowTask {
  return {
    ...planned,
    status: "pending",
    started_at: null,
    finished_at: null,
    duration_ms: null,
    result: null,
    status_reason: null,
  };
}
