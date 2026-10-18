"use client";

import type { WorkflowRun } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { groupByLevel } from "@/lib/workflow/graph";
import { timelineBars, type Segment, type TimelineBar } from "@/lib/workflow/metrics";
import { TOOL_LABELS } from "@/lib/tool-labels";
import { StatusIcon, TASK_STATUS } from "@/components/ui/status";

const BAR_COLOR: Record<string, string> = {
  running: "bg-accent",
  completed: "bg-ok",
  failed: "bg-fail",
  cancelled: "bg-line-strong",
};

/**
 * The plan and its execution in one view: tasks grouped into dependency steps,
 * each with a bar on a shared time axis. Bars in the same step overlap in time,
 * which is what running in parallel looks like.
 */
export function RunGraph({ run, now }: { run: WorkflowRun; now: number | null }) {
  const { bars, spanMs } = timelineBars(run, now);
  const barById = new Map(bars.map((b) => [b.task.id, b]));
  const titleById = new Map(run.tasks.map((t) => [t.id, t.title]));
  const steps = groupByLevel(run.tasks);
  const started = run.started_at !== null;

  return (
    <div className="space-y-4">
      {steps.map((tasks, index) => (
        <section key={index} aria-label={`Step ${index + 1}`}>
          <div className="mb-1.5 flex items-baseline gap-2">
            <h4 className="text-[13px] font-semibold">Step {index + 1}</h4>
            {tasks.length > 1 && <span className="text-[12px] text-faint">{tasks.length} run in parallel</span>}
          </div>
          <ol className="space-y-1">
            {tasks.map((task) => {
              const bar = barById.get(task.id)!;
              const meta = TASK_STATUS[task.status];
              return (
                <li
                  key={task.id}
                  data-testid={`task-${task.id}`}
                  data-status={task.status}
                  data-started-ms={offsetMs(run.started_at, task.started_at)}
                  data-finished-ms={offsetMs(run.started_at, task.finished_at)}
                  className="grid grid-cols-[minmax(0,1fr)_minmax(4rem,32%)_2.75rem] items-center gap-x-3 rounded-lg px-1 py-1.5"
                >
                  <div className="flex min-w-0 items-start gap-2">
                    <StatusIcon meta={meta} className="mt-0.5 size-4" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium leading-snug">{task.title}</p>
                      <p className="text-[12px] leading-snug text-faint">{TOOL_LABELS[task.tool_name]}</p>
                      {task.depends_on.length > 0 && (
                        <p className="text-[12px] leading-snug text-faint">
                          Waits for {joinList(task.depends_on.map((d) => titleById.get(d) ?? d))}
                        </p>
                      )}
                      <span className="sr-only">Status: {meta.label}</span>
                    </div>
                  </div>
                  <Track bar={bar} started={started} />
                  <span className="tabular text-right text-[12px] text-muted">
                    {bar.durationMs === null ? "–" : formatDuration(bar.durationMs)}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      ))}

      {started && (
        <div aria-hidden className="grid grid-cols-[minmax(0,1fr)_minmax(4rem,32%)_2.75rem] gap-x-3 px-1">
          <span />
          <div className="tabular flex justify-between border-t border-line pt-1 text-[11px] text-faint">
            <span>0s</span>
            <span>{formatDuration(spanMs / 2)}</span>
            <span>{formatDuration(spanMs)}</span>
          </div>
          <span />
        </div>
      )}
    </div>
  );
}

function Track({ bar, started }: { bar: TimelineBar; started: boolean }) {
  const { task } = bar;
  const place = (seg: Segment) => ({ left: `${seg.offset * 100}%`, width: `max(${seg.width * 100}%, 6px)` });
  return (
    <div className="relative h-2.5 rounded-full bg-sunk ring-1 ring-inset ring-line" aria-hidden>
      {!started && <div className="absolute inset-0 rounded-full border border-dashed border-line-strong" />}
      {bar.wait && (
        <div className="hatch absolute inset-y-0 rounded-full transition-[width,left] duration-150 ease-linear" style={place(bar.wait)} />
      )}
      {bar.work && (
        <div
          className={`absolute inset-y-0 rounded-full transition-[width,left] duration-150 ease-linear ${BAR_COLOR[task.status] ?? "bg-line-strong"}`}
          style={place(bar.work)}
        />
      )}
    </div>
  );
}

function joinList(items: string[]): string {
  return items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

/** Milliseconds from run start, exposed as data attributes for tests and debugging. */
function offsetMs(runStart: string | null, at: string | null): number | undefined {
  return runStart && at ? Date.parse(at) - Date.parse(runStart) : undefined;
}
