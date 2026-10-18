import type { ToolName } from "@/lib/api/types";

/** User-facing names for tools. */
export const TOOL_LABELS: Record<ToolName, string> = {
  get_weather: "Weather",
  calendar_list_events: "Google Calendar",
  gmail_search: "Gmail",
  web_search: "Web search",
  document_search: "Documents",
  summarize: "AI summary",
  telegram_send_message: "Telegram",
};
