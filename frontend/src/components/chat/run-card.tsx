"use client";

import { Hand, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RUN_STATUS, StatusPill, TASK_STATUS } from "@/components/ui/status";
import type { WorkflowRun } from "@/lib/api/types";
import { failureReason, pendingApproval, progress } from "@/lib/workflow/metrics";

const SEGMENT: Record<string, string> = {
  pending: "bg-line",
  running: "bg-accent motion-safe:animate-pulse",
  waiting_for_approval: "hatch",
  completed: "bg-ok",
  failed: "bg-fail",
  skipped: "bg-line-strong",
  cancelled: "bg-line-strong",
};

/** Compact view of a run inside the conversation. Full details live in the run panel. */
export function RunCard({
  run,
  selected,
  onOpen,
  onStart,
}: {
  run: WorkflowRun;
  selected: boolean;
  onOpen: (focusApproval?: boolean) => void;
  onStart: () => void;
}) {
  const { done, total } = progress(run);
  const approval = pendingApproval(run);
  const failure = failureReason(run);

  return (
    <div
      data-testid="run-card"
      className={`mt-3 rounded-xl bg-surface p-3.5 ring-1 transition-shadow ${selected ? "ring-accent/50 shadow-sm" : "ring-line"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusPill meta={RUN_STATUS[run.status]} />
        <span className="tabular text-[13px] text-muted">
          {done} of {total} steps
        </span>
      </div>

      <ol aria-label="Step status" className="mt-3 flex gap-1">
        {run.tasks.map((task) => (
          <li key={task.id} title={`${task.title}: ${TASK_STATUS[task.status].label}`} className="h-1.5 flex-1">
            <span className={`block h-full rounded-full ${SEGMENT[task.status]}`} />
            <span className="sr-only">
              {task.title}: {TASK_STATUS[task.status].label}
            </span>
          </li>
        ))}
      </ol>

      {approval && (
        <p className="mt-3 flex items-center gap-2 text-sm font-medium text-decide-ink">
          <Hand className="size-4" aria-hidden />
          Waiting for you to approve the Telegram message.
        </p>
      )}
      {run.status === "completed" && run.summary && <p className="mt-3 whitespace-pre-wrap text-sm">{run.summary}</p>}
      {failure && <p className="mt-3 text-sm text-fail">{failure}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        {run.status === "planned" && (
          <Button variant="primary" size="sm" onClick={onStart}>
            <Play className="size-3.5" aria-hidden />
            Run plan
          </Button>
        )}
        {approval ? (
          <Button variant="decide" size="sm" onClick={() => onOpen(true)}>
            Review message
          </Button>
        ) : (
          <Button size="sm" onClick={() => onOpen()}>
            {run.status === "planned" ? "View plan" : "View details"}
          </Button>
        )}
      </div>
    </div>
  );
}
