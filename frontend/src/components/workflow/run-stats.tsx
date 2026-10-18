import type { UsageStats, WorkflowRun } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { parallelSavingMs, progress } from "@/lib/workflow/metrics";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-[12px] text-muted">{label}</dt>
      <dd className="tabular text-lg font-semibold tracking-tight">{value}</dd>
    </div>
  );
}

export function RunStats({ run, elapsed, stats }: { run: WorkflowRun | null; elapsed: number | null; stats: UsageStats | null }) {
  return (
    <div className="space-y-4">
      {run && (
        <dl aria-label="This run" className="grid grid-cols-3 gap-3">
          <Stat label="Elapsed" value={formatDuration(elapsed)} />
          <Stat label="Steps done" value={`${progress(run).done} of ${progress(run).total}`} />
          <Stat label="Saved by parallel" value={formatDuration(parallelSavingMs(run.tasks))} />
        </dl>
      )}
      {stats && (
        <dl aria-label="All runs" className="grid grid-cols-3 gap-3 border-t border-line pt-3">
          <Stat label="Runs" value={`${stats.completed_runs} of ${stats.total_runs} done`} />
          <Stat label="Tool calls" value={String(stats.tool_calls)} />
          <Stat label="Approved" value={`${stats.approvals_approved} of ${stats.approvals_requested}`} />
        </dl>
      )}
    </div>
  );
}
