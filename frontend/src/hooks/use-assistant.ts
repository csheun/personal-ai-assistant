"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { ConnectionStatus, WorkflowClient } from "@/lib/api/client";
import { ApiError, type ApprovalDecision, type ID, type RunStatus } from "@/lib/api/types";
import { assistantReducer, initialState } from "@/lib/state/assistant-state";

const FINISHED: ReadonlySet<RunStatus> = new Set(["completed", "failed", "cancelled"]);

const messageOf = (error: unknown) =>
  error instanceof ApiError ? error.message : "Something went wrong. Check your connection and try again.";

/**
 * Connects the pure state reducer to a WorkflowClient: loads data, sends messages,
 * and keeps one event stream open per unfinished run. Works the same against the
 * in-browser mock and FastAPI.
 */
export function useAssistantController(client: WorkflowClient) {
  const [state, dispatch] = useReducer(assistantReducer, initialState);
  const [actionError, setActionError] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionStatus>("checking");
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

  useEffect(() => client.watchConnection(setConnection), [client]);

  // Back online after an outage: reload the sidebar if it failed to load meanwhile.
  const wasOffline = useRef(false);
  useEffect(() => {
    if (connection === "offline") wasOffline.current = true;
    if (connection === "online" && wasOffline.current) {
      wasOffline.current = false;
      if (stateRef.current.conversationsStatus === "error") loadConversations();
      refreshStats();
    }
  }, [connection, loadConversations, refreshStats]);

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

  // The open conversation lives in the URL (?c=…), so a refresh reopens it: messages and the
  // run snapshot are fetched again and the event stream resumes from the snapshot's last event.
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("c");
    if (fromUrl) selectConversation(fromUrl);
  }, [selectConversation]);

  useEffect(() => {
    const url = new URL(window.location.href);
    const id = state.activeConversationId;
    if ((url.searchParams.get("c") ?? null) === id) return;
    if (id) url.searchParams.set("c", id);
    else url.searchParams.delete("c");
    window.history.replaceState(null, "", url);
  }, [state.activeConversationId]);

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

  // Commands return a fresh snapshot; applying it keeps the UI correct even if the event stream
  // is down. The reducer ignores snapshots older than what the stream already delivered.
  const startRun = useCallback(
    (runId: ID) => command(() => client.startRun(runId).then((run) => dispatch({ type: "run/loaded", run }))),
    [client, command],
  );
  const cancelRun = useCallback(
    (runId: ID) => command(() => client.cancelRun(runId).then((run) => dispatch({ type: "run/loaded", run }))),
    [client, command],
  );
  const resolveApproval = useCallback(
    (runId: ID, approvalId: ID, decision: ApprovalDecision) =>
      command(() => client.resolveApproval(runId, approvalId, decision)),
    [client, command],
  );

  // One live subscription per unfinished run; closed once the run finishes.
  useEffect(() => {
    const subs = subscriptions.current;
    for (const run of Object.values(state.runs)) {
      const finished = FINISHED.has(run.status);
      if (!finished && !subs.has(run.id)) {
        const unsubscribe = client.subscribeToRun(
          run.id,
          {
            onEvent: (event) => dispatch({ type: "run/event", event }),
            onStatusChange: (status) => dispatch({ type: "run/stream", runId: run.id, status }),
          },
          run.last_event_id,
        );
        subs.set(run.id, unsubscribe);
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
    connection,
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
