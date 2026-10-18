"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

import { useAssistantController, type AssistantController } from "@/hooks/use-assistant";
import { createApiClient, type ApiClient } from "@/lib/api";

const AssistantContext = createContext<AssistantController | null>(null);

export function AssistantProvider({ children, client }: { children: ReactNode; client?: ApiClient }) {
  const [api] = useState(() => client ?? createApiClient());
  const controller = useAssistantController(api);
  return <AssistantContext.Provider value={controller}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantController {
  const value = useContext(AssistantContext);
  if (!value) throw new Error("useAssistant must be used inside <AssistantProvider>");
  return value;
}
