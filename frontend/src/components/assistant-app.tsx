"use client";

import { useState } from "react";

import { AssistantProvider, useAssistant } from "./assistant-provider";
import { ChatPanel } from "./chat/chat-panel";
import { Sidebar } from "./layout/sidebar";
import { Sheet } from "./ui/sheet";
import { RunPanel } from "./workflow/run-panel";

export function AssistantApp() {
  return (
    <AssistantProvider>
      <Shell />
    </AssistantProvider>
  );
}

const isDesktop = () => typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches;

/**
 * Desktop (≥1024px): sidebar | chat | run panel.
 * Mobile: chat only; the sidebar is a drawer and the run opens as a bottom sheet.
 */
function Shell() {
  const { selectRun } = useAssistant();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [runSheetOpen, setRunSheetOpen] = useState(false);

  const openRun = (runId: string, focusApproval = false) => {
    selectRun(runId);
    if (!isDesktop()) {
      setRunSheetOpen(true);
    } else if (focusApproval) {
      requestAnimationFrame(() =>
        document.querySelector("#run-panel [id^='approval-']")?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    }
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside className="hidden w-[256px] shrink-0 border-r border-line lg:flex">
        <Sidebar />
      </aside>

      <main className="min-w-0 flex-1 bg-bg">
        <ChatPanel onOpenSidebar={() => setDrawerOpen(true)} onOpenRun={openRun} />
      </main>

      <aside
        id="run-panel"
        aria-label="Workflow run"
        className="hidden w-[400px] shrink-0 overflow-y-auto border-l border-line bg-surface lg:block xl:w-[440px]"
      >
        <RunPanel />
      </aside>

      <Sheet open={drawerOpen} onClose={() => setDrawerOpen(false)} side="left" title="Conversations">
        <Sidebar onNavigate={() => setDrawerOpen(false)} />
      </Sheet>
      <Sheet open={runSheetOpen} onClose={() => setRunSheetOpen(false)} side="bottom" title="Workflow run">
        <RunPanel />
      </Sheet>
    </div>
  );
}
