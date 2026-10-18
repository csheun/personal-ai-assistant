"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { ApiClient } from "@/lib/api/client";
import { ApiError, type ApprovalDecision, type ID, type RunStatus } from "@/lib/api/types";
import { assistantReducer, initialState } from "@/lib/state/assistant-state";

const FINISHED: ReadonlySet<RunStatus> = new Set(["completed", "failed", "cancelled"]);

const messageOf = (error: unknown) =>
  error instanceof ApiError ? error.message : "Something went wrong. Check your connection and try again.";

/**
 * Connects the pure state reducer to an ApiClient: loads data, sends messages,
 * and keeps one event subscription open per unfinished run.
 */
export function useAssistantController(client: ApiClient) {
  const [state, dispatch] = useReducer(assistantReducer, initialState);
  const [actionError, setActionError] = useState<string | null>(null);
  const subscriptions = useRef(new Map<ID, () => void>());
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  });

  const refreshStats = useCallback(() => {
    client.getStats().then((stats) => dispatch({ type: "stats/loaded", stats }), () => {});
  }, [client]);

  const loadConversations = useCallback(() => {
    dispatch({ type: "conversations/loading" });
    client.listConversations().then(
      (conversations) => dispatch({ type: "conversations/loaded", conversations }),
      () => dispatch({ type: "conversations/failed" }),
    );
  }, [client]);

  useEffect(() => {
    loadConversations();
    refreshStats();
  }, [loadConversations, refreshStats]);

  const loadMessages = useCallback(
    async (conversationId: ID) => {
      dispatch({ type: "messages/loading", conversationId });
      try {
        const messages = await client.listMessages(conversationId);
        const runIds = messages.flatMap((m) => (m.run_id ? [m.run_id] : []));
        const runs = await Promise.all(runIds.map((id) => client.getRun(id)));
        runs.forEach((run) => dispatch({ type: "run/loaded", run }));
        dispatch({ type: "messages/loaded", conversationId, messages });
      } catch {
        dispatch({ type: "messages/failed", conversationId });
      }
    },
    [client],
  );

  const selectConversation = useCallback(
    (id: ID | null) => {
      dispatch({ type: "conversation/selected", id });
      if (id && stateRef.current.messagesStatus[id] !== "ready") void loadMessages(id);
    },
    [loadMessages],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      dispatch({ type: "send/started", text });
      try {
        const response = await client.sendMessage({ conversation_id: stateRef.current.activeConversationId, message: text });
        dispatch({ type: "send/succeeded", response });
      } catch (error) {
        dispatch({ type: "send/failed", text, message: messageOf(error) });
      }
    },
    [client],
  );

  /** Wraps a run command so failures (e.g. 409 conflicts) surface as a dismissible notice. */
  const command = useCallback(
    (fn: () => Promise<unknown>) => {
      setActionError(null);
      fn().catch((error) => setActionError(messageOf(error)));
    },
    [],
  );

  const startRun = useCallback((runId: ID) => command(() => client.startRun(runId)), [client, command]);
  const cancelRun = useCallback((runId: ID) => command(() => client.cancelRun(runId)), [client, command]);
  const resolveApproval = useCallback(
    (approvalId: ID, decision: ApprovalDecision) => command(() => client.resolveApproval(approvalId, decision)),
    [client, command],
  );

  // One live subscription per unfinished run; closed once the run finishes.
  useEffect(() => {
    const subs = subscriptions.current;
    for (const run of Object.values(state.runs)) {
      const finished = FINISHED.has(run.status);
      if (!finished && !subs.has(run.id)) {
        subs.set(run.id, client.subscribeToRun(run.id, (event) => dispatch({ type: "run/event", event }), run.last_event_seq));
      } else if (finished && subs.has(run.id)) {
        subs.get(run.id)!();
        subs.delete(run.id);
        refreshStats();
      }
    }
  }, [state.runs, client, refreshStats]);

  useEffect(() => {
    const subs = subscriptions.current;
    return () => {
      subs.forEach((unsubscribe) => unsubscribe());
      subs.clear();
    };
  }, []);

  return {
    state,
    actionError,
    dismissActionError: () => setActionError(null),
    loadConversations,
    selectConversation,
    retryMessages: loadMessages,
    sendMessage,
    dismissSendError: () => dispatch({ type: "send/errorDismissed" }),
    selectRun: (id: ID | null) => dispatch({ type: "run/selected", id }),
    startRun,
    cancelRun,
    resolveApproval,
  };
}

export type AssistantController = ReturnType<typeof useAssistantController>;
