/**
 * App-level UI state as a pure reducer. No fetching, no timers — the hook in
 * `hooks/use-assistant.ts` performs effects and dispatches these actions.
 */
import type {
  ChatMessage,
  Conversation,
  ID,
  SendMessageResponse,
  UsageStats,
  WorkflowEvent,
  WorkflowRun,
} from "@/lib/api/types";
import { applyEvent } from "@/lib/workflow/reducer";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

export interface AssistantState {
  conversations: Conversation[];
  conversationsStatus: LoadStatus;
  activeConversationId: ID | null;
  messages: Record<ID, ChatMessage[]>;
  messagesStatus: Record<ID, LoadStatus>;
  runs: Record<ID, WorkflowRun>;
  /** Run shown in the workflow panel. */
  selectedRunId: ID | null;
  /** A message that is being sent (shown optimistically). */
  pending: { conversationId: ID | null; text: string } | null;
  sendError: { text: string; message: string } | null;
  stats: UsageStats | null;
}

export const initialState: AssistantState = {
  conversations: [],
  conversationsStatus: "idle",
  activeConversationId: null,
  messages: {},
  messagesStatus: {},
  runs: {},
  selectedRunId: null,
  pending: null,
  sendError: null,
  stats: null,
};

export type AssistantAction =
  | { type: "conversations/loading" }
  | { type: "conversations/loaded"; conversations: Conversation[] }
  | { type: "conversations/failed" }
  | { type: "conversation/selected"; id: ID | null }
  | { type: "messages/loading"; conversationId: ID }
  | { type: "messages/loaded"; conversationId: ID; messages: ChatMessage[] }
  | { type: "messages/failed"; conversationId: ID }
  | { type: "send/started"; text: string }
  | { type: "send/succeeded"; response: SendMessageResponse }
  | { type: "send/failed"; text: string; message: string }
  | { type: "send/errorDismissed" }
  | { type: "run/loaded"; run: WorkflowRun }
  | { type: "run/event"; event: WorkflowEvent }
  | { type: "run/selected"; id: ID | null }
  | { type: "stats/loaded"; stats: UsageStats };

export function assistantReducer(state: AssistantState, action: AssistantAction): AssistantState {
  switch (action.type) {
    case "conversations/loading":
      return { ...state, conversationsStatus: "loading" };
    case "conversations/loaded":
      return { ...state, conversations: action.conversations, conversationsStatus: "ready" };
    case "conversations/failed":
      return { ...state, conversationsStatus: "error" };

    case "conversation/selected": {
      if (action.id === state.activeConversationId) return state;
      return {
        ...state,
        activeConversationId: action.id,
        selectedRunId: action.id ? latestRunId(state.messages[action.id]) : null,
        sendError: null,
      };
    }

    case "messages/loading":
      return { ...state, messagesStatus: { ...state.messagesStatus, [action.conversationId]: "loading" } };
    case "messages/loaded":
      return {
        ...state,
        messages: { ...state.messages, [action.conversationId]: action.messages },
        messagesStatus: { ...state.messagesStatus, [action.conversationId]: "ready" },
        selectedRunId:
          state.activeConversationId === action.conversationId ? latestRunId(action.messages) : state.selectedRunId,
      };
    case "messages/failed":
      return { ...state, messagesStatus: { ...state.messagesStatus, [action.conversationId]: "error" } };

    case "send/started":
      return { ...state, pending: { conversationId: state.activeConversationId, text: action.text }, sendError: null };

    case "send/succeeded": {
      const { conversation, user_message, assistant_message, run } = action.response;
      const others = state.conversations.filter((c) => c.id !== conversation.id);
      const existing = state.messages[conversation.id] ?? [];
      return {
        ...state,
        pending: null,
        conversations: [conversation, ...others],
        activeConversationId: conversation.id,
        messages: { ...state.messages, [conversation.id]: [...existing, user_message, assistant_message] },
        messagesStatus: { ...state.messagesStatus, [conversation.id]: "ready" },
        runs: run ? { ...state.runs, [run.id]: run } : state.runs,
        selectedRunId: run ? run.id : state.selectedRunId,
      };
    }
    case "send/failed":
      return { ...state, pending: null, sendError: { text: action.text, message: action.message } };
    case "send/errorDismissed":
      return { ...state, sendError: null };

    case "run/loaded": {
      // Never let an older snapshot overwrite state built from newer events.
      const current = state.runs[action.run.id];
      if (current && current.last_event_seq > action.run.last_event_seq) return state;
      return { ...state, runs: { ...state.runs, [action.run.id]: action.run } };
    }

    case "run/event": {
      const { event } = action;
      const run = state.runs[event.run_id];
      // Ignore events for unknown runs, duplicates and replays already in the snapshot.
      if (!run || event.seq <= run.last_event_seq) return state;
      return { ...state, runs: { ...state.runs, [event.run_id]: applyEvent(run, event) } };
    }

    case "run/selected":
      return { ...state, selectedRunId: action.id };

    case "stats/loaded":
      return { ...state, stats: action.stats };
  }
}

function latestRunId(messages: ChatMessage[] | undefined): ID | null {
  return messages?.findLast((m) => m.run_id)?.run_id ?? null;
}
