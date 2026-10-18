"use client";

import { CalendarDays, CloudSun, FileText, Globe, Mail, Plus, Send, type LucideIcon } from "lucide-react";

import { useAssistant } from "@/components/assistant-provider";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useNow } from "@/hooks/use-now";
import { apiMode, type ConnectionStatus } from "@/lib/api";
import { formatRelative } from "@/lib/format";

const INTEGRATIONS: { name: string; icon: LucideIcon; note: string }[] = [
  { name: "Weather", icon: CloudSun, note: "Mock data" },
  { name: "Google Calendar", icon: CalendarDays, note: "Mock data" },
  { name: "Gmail", icon: Mail, note: "Mock data" },
  { name: "Web search", icon: Globe, note: "Mock data" },
  { name: "Documents", icon: FileText, note: "Mock data" },
  { name: "Telegram", icon: Send, note: "Asks before sending" },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { state, connection, selectConversation, loadConversations } = useAssistant();
  const now = useNow(false);

  const open = (id: string | null) => {
    selectConversation(id);
    onNavigate?.();
  };

  return (
    <nav aria-label="Conversations" className="flex h-full min-h-0 w-full flex-col gap-5 px-3 py-4">
      <div className="flex items-center gap-2.5 px-2">
        <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-ink text-[13px] font-bold text-bg">
          PA
        </span>
        <span className="text-[15px] font-semibold tracking-tight">Personal Assistant</span>
      </div>

      <Button variant="primary" className="w-full" onClick={() => open(null)}>
        <Plus className="size-4" aria-hidden />
        New chat
      </Button>

      <section aria-labelledby="history-heading" className="flex min-h-0 flex-1 flex-col">
        <h2 id="history-heading" className="px-2 pb-1.5 text-[13px] font-semibold text-muted">
          Recent
        </h2>
        <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          {state.conversationsStatus === "loading" || state.conversationsStatus === "idle" ? (
            <ul aria-label="Loading conversations" className="space-y-1.5 px-2 pt-1">
              {[0, 1, 2].map((i) => (
                <li key={i} className="h-9 animate-pulse rounded-lg bg-sunk" />
              ))}
            </ul>
          ) : state.conversationsStatus === "error" ? (
            <div role="alert" className="space-y-2 px-2 text-sm text-muted">
              <p>Couldn&apos;t load your conversations.</p>
              <Button size="sm" onClick={loadConversations}>
                Try again
              </Button>
            </div>
          ) : state.conversations.length === 0 ? (
            <p className="px-2 text-sm text-muted">Your conversations will appear here.</p>
          ) : (
            <ul className="space-y-0.5">
              {state.conversations.map((c) => {
                const active = c.id === state.activeConversationId;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => open(c.id)}
                      aria-current={active ? "page" : undefined}
                      className={`block w-full rounded-lg px-2 py-2 text-left transition-colors ${
                        active ? "bg-surface shadow-sm ring-1 ring-line" : "hover:bg-surface/60"
                      }`}
                    >
                      <span className="block truncate text-sm font-medium">{c.title}</span>
                      {now !== null && (
                        <span className="block text-[12px] text-faint">{formatRelative(c.updated_at, now)}</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>

      <section aria-labelledby="integrations-heading">
        <h2 id="integrations-heading" className="px-2 pb-1.5 text-[13px] font-semibold text-muted">
          Integrations
        </h2>
        <ul className="space-y-0.5">
          {INTEGRATIONS.map(({ name, icon: Icon, note }) => (
            <li key={name} className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm">
              <Icon className="size-4 text-muted" aria-hidden />
              <span className="flex-1 truncate">{name}</span>
              <span className={`text-[12px] ${name === "Telegram" ? "text-decide-ink" : "text-faint"}`}>{note}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex items-center justify-between gap-2 border-t border-line px-2 pt-3">
        {apiMode() === "http" ? (
          <ConnectionNote status={connection} />
        ) : (
          <span className="text-[12px] text-faint">Demo mode, runs in your browser</span>
        )}
        <ThemeToggle />
      </div>
    </nav>
  );
}

const CONNECTION: Record<ConnectionStatus, { text: string; dot: string; tone: string }> = {
  checking: { text: "Connecting to the backend…", dot: "bg-line-strong", tone: "text-faint" },
  online: { text: "Backend connected, tools mocked", dot: "bg-ok", tone: "text-faint" },
  offline: { text: "Can't reach the backend. Retrying…", dot: "bg-fail", tone: "text-fail" },
};

/** Live backend reachability (HTTP mode). The text carries the meaning; the dot is decoration. */
function ConnectionNote({ status }: { status: ConnectionStatus }) {
  const { text, dot, tone } = CONNECTION[status];
  return (
    <p role="status" className={`flex min-w-0 items-center gap-1.5 text-[12px] ${tone}`}>
      <span aria-hidden className={`size-1.5 shrink-0 rounded-full ${dot}`} />
      {text}
    </p>
  );
}
