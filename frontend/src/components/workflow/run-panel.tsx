"use client";

import { Play, Square, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAssistant } from "@/components/assistant-provider";
import { Button } from "@/components/ui/button";
import { RUN_STATUS, StatusPill, TASK_STATUS } from "@/components/ui/status";
import { useNow } from "@/hooks/use-now";
import type { WorkflowRun } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { elapsedMs, failureReason, pendingApproval, progress } from "@/lib/workflow/metrics";
import { ApprovalCard } from "./approval-card";
import { RunGraph } from "./run-graph";
import { RunStats } from "./run-stats";
import { TaskResults } from "./task-results";

const LIVE = new Set(["running", "waiting_for_approval"]);

export function RunPanel() {
  const { state, startRun, cancelRun, resolveApproval, actionError, dismissActionError } = useAssistant();
  const run = state.selectedRunId ? state.runs[state.selectedRunId] : null;
  const now = useNow(!!run && LIVE.has(run.status));
  const elapsed = run ? elapsedMs(run, now) : null;

  if (!run) {
    return (
      <div className="flex h-full flex-col gap-6 p-5">
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
          <Workflow className="size-6 text-faint" aria-hidden />
          <p className="font-semibold">No run selected</p>
          <p className="max-w-[28ch] text-sm text-muted">When I plan something, the steps appear here and you can watch them run.</p>
        </div>
        <RunStats run={null} elapsed={null} stats={state.stats} />
      </div>
    );
  }

  const approval = pendingApproval(run);
  const { done, total } = progress(run);
  const failure = failureReason(run);

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-10 space-y-3 border-b border-line bg-surface/95 px-5 py-4 backdrop-blur">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-[17px] font-semibold leading-snug tracking-tight">{run.goal}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <StatusPill meta={RUN_STATUS[run.status]} />
          <span className="tabular text-sm text-muted">
            {run.started_at ? `${formatDuration(elapsed)} elapsed` : `${total} steps planned`}
            {run.started_at && `, ${done} of ${total} steps done`}
          </span>
          <div className="ml-auto flex gap-2">
            {run.status === "planned" && (
              <Button variant="primary" size="sm" onClick={() => startRun(run.id)}>
                <Play className="size-3.5" aria-hidden />
                Run plan
              </Button>
            )}
            {(run.status === "planned" || LIVE.has(run.status)) && (
              <Button variant="danger" size="sm" onClick={() => cancelRun(run.id)}>
                <Square className="size-3" aria-hidden />
                {run.status === "planned" ? "Discard" : "Cancel run"}
              </Button>
            )}
          </div>
        </div>
        {actionError && (
          <p role="alert" className="flex items-center justify-between gap-2 rounded-lg bg-fail-soft px-3 py-2 text-sm text-fail">
            {actionError}
            <button type="button" className="font-semibold underline" onClick={dismissActionError}>
              Dismiss
            </button>
          </p>
        )}
      </header>

      <div className="flex-1 space-y-6 px-5 py-5">
        {approval && <ApprovalCard key={approval.id} approval={approval} onResolve={resolveApproval} />}

        {run.status === "completed" && run.summary && (
          <section aria-labelledby="summary-heading" className="rounded-xl bg-ok-soft/60 p-4 ring-1 ring-ok/20">
            <h3 id="summary-heading" className="mb-1 text-sm font-semibold text-ok">
              Summary
            </h3>
            <p className="whitespace-pre-wrap text-sm">{run.summary}</p>
          </section>
        )}
        {failure && (
          <section role="status" className="rounded-xl bg-fail-soft p-4 text-sm ring-1 ring-fail/20">
            <h3 className="mb-1 font-semibold text-fail">The run stopped</h3>
            <p>{failure}</p>
          </section>
        )}

        <section aria-labelledby="plan-heading">
          <div className="mb-3 flex items-baseline justify-between">
            <h3 id="plan-heading" className="font-semibold">
              {run.started_at ? "Timeline" : "Proposed plan"}
            </h3>
            {!run.started_at && run.status === "planned" && (
              <span className="text-[12px] text-faint">Nothing runs until you start it</span>
            )}
          </div>
          <RunGraph run={run} now={now} />
        </section>

        {run.started_at && (
          <section aria-labelledby="results-heading">
            <h3 id="results-heading" className="mb-3 font-semibold">
              Tool results
            </h3>
            <TaskResults tasks={run.tasks} />
          </section>
        )}

        <section aria-labelledby="stats-heading">
          <h3 id="stats-heading" className="mb-3 font-semibold">
            Statistics
          </h3>
          <RunStats run={run} elapsed={elapsed} stats={state.stats} />
        </section>
      </div>

      <StatusAnnouncer run={run} />
    </div>
  );
}

/** Announces task status changes to screen readers without moving focus. */
function StatusAnnouncer({ run }: { run: WorkflowRun }) {
  const previous = useRef<Map<string, string> | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const current = new Map(run.tasks.map((t) => [t.id, t.status]));
    const before = previous.current;
    previous.current = current;
    if (!before) return;
    const changed = run.tasks.filter((t) => before.get(t.id) !== t.status);
    if (changed.length) setMessage(changed.map((t) => `${t.title}: ${TASK_STATUS[t.status].label}`).join(". "));
  }, [run]);

  return (
    <p className="sr-only" aria-live="polite">
      {message}
    </p>
  );
}
