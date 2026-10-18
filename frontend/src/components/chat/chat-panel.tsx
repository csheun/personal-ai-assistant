"use client";

import { AlertCircle, Menu, Workflow } from "lucide-react";
import { useEffect, useRef } from "react";

import { useAssistant } from "@/components/assistant-provider";
import { Button, IconButton } from "@/components/ui/button";
import { RUN_STATUS, StatusIcon } from "@/components/ui/status";
import type { ChatMessage } from "@/lib/api/types";
import { Composer } from "./composer";
import { EmptyState } from "./empty-state";
import { RunCard } from "./run-card";

export function ChatPanel({
  onOpenSidebar,
  onOpenRun,
}: {
  onOpenSidebar: () => void;
  onOpenRun: (runId: string, focusApproval?: boolean) => void;
}) {
  const { state, sendMessage, dismissSendError, retryMessages, startRun } = useAssistant();
  const id = state.activeConversationId;
  const conversation = state.conversations.find((c) => c.id === id) ?? null;
  const messages = id ? (state.messages[id] ?? []) : [];
  const status = id ? state.messagesStatus[id] : "ready";
  const pending = state.pending && state.pending.conversationId === id ? state.pending : null;
  const selectedRun = state.selectedRunId ? state.runs[state.selectedRunId] : null;

  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length, pending, state.sendError]);

  const showEmpty = !id && !pending && !state.sendError;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 sm:px-4">
        <IconButton label="Open conversations" className="lg:hidden" onClick={onOpenSidebar}>
          <Menu className="size-5" aria-hidden />
        </IconButton>
        <h2 className="min-w-0 flex-1 truncate font-semibold">{conversation?.title ?? "New chat"}</h2>
        {selectedRun && (
          <Button size="sm" className="lg:hidden" onClick={() => onOpenRun(selectedRun.id)} aria-label="Show run details">
            <StatusIcon meta={RUN_STATUS[selectedRun.status]} className="size-3.5" />
            <Workflow className="size-3.5" aria-hidden />
            Run
          </Button>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 sm:px-6" aria-live="polite" aria-busy={status === "loading"}>
        {showEmpty ? (
          <EmptyState onPick={sendMessage} disabled={!!state.pending} />
        ) : (
          <ol className="mx-auto w-full max-w-3xl space-y-6 py-6" aria-label="Messages">
            {status === "loading" && (
              <li aria-label="Loading messages" className="space-y-3">
                <div className="ml-auto h-10 w-2/3 animate-pulse rounded-2xl bg-surface" />
                <div className="h-24 w-5/6 animate-pulse rounded-2xl bg-surface" />
              </li>
            )}
            {status === "error" && id && (
              <li role="alert" className="flex items-center gap-3 rounded-xl bg-fail-soft p-3 text-sm text-fail">
                <AlertCircle className="size-4" aria-hidden />
                <span className="flex-1">Couldn&apos;t load this conversation.</span>
                <Button size="sm" onClick={() => retryMessages(id)}>
                  Try again
                </Button>
              </li>
            )}
            {messages.map((message) => (
              <MessageItem key={message.id} message={message} onOpenRun={onOpenRun} onStartRun={startRun} />
            ))}
            {pending && (
              <>
                <UserBubble text={pending.text} />
                <li className="flex items-center gap-2 text-sm text-muted" role="status">
                  <span className="flex gap-1" aria-hidden>
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="size-1.5 rounded-full bg-faint motion-safe:animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </span>
                  Planning…
                </li>
              </>
            )}
            {state.sendError && (
              <>
                <UserBubble text={state.sendError.text} failed />
                <li role="alert" className="rounded-xl bg-fail-soft p-3 text-sm text-fail ring-1 ring-fail/20">
                  <p className="font-semibold">Message not sent</p>
                  <p>{state.sendError.message}</p>
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" onClick={() => sendMessage(state.sendError!.text)}>
                      Send again
                    </Button>
                    <Button size="sm" variant="ghost" onClick={dismissSendError}>
                      Dismiss
                    </Button>
                  </div>
                </li>
              </>
            )}
            <div ref={endRef} />
          </ol>
        )}
      </div>

      <div className="shrink-0 px-3 pb-3 pt-2 sm:px-6 sm:pb-5">
        <Composer onSend={sendMessage} disabled={!!state.pending} />
      </div>
    </div>
  );
}

function UserBubble({ text, failed = false }: { text: string; failed?: boolean }) {
  return (
    <li className="flex justify-end">
      <p
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-accent-ink ${failed ? "opacity-60" : ""}`}
      >
        {text}
      </p>
    </li>
  );
}

function MessageItem({
  message,
  onOpenRun,
  onStartRun,
}: {
  message: ChatMessage;
  onOpenRun: (runId: string, focusApproval?: boolean) => void;
  onStartRun: (runId: string) => void;
}) {
  const { state } = useAssistant();
  if (message.role === "user") return <UserBubble text={message.content} />;

  const run = message.run_id ? state.runs[message.run_id] : null;
  return (
    <li className="max-w-[92%] motion-safe:animate-rise">
      <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
      {run && (
        <RunCard
          run={run}
          selected={state.selectedRunId === run.id}
          onOpen={(focusApproval) => onOpenRun(run.id, focusApproval)}
          onStart={() => onStartRun(run.id)}
        />
      )}
    </li>
  );
}
