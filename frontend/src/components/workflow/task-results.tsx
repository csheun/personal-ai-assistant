import { ChevronRight } from "lucide-react";

import { StatusPill, TASK_STATUS } from "@/components/ui/status";
import type { WorkflowTask } from "@/lib/api/types";
import { TOOL_LABELS } from "@/lib/tool-labels";

export function TaskResults({ tasks }: { tasks: WorkflowTask[] }) {
  return (
    <ul className="divide-y divide-line rounded-xl bg-surface ring-1 ring-line">
      {tasks.map((task) => (
        <li key={task.id}>
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden">
              <ChevronRight className="size-4 text-faint transition-transform group-open:rotate-90" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{task.title}</span>
              <StatusPill meta={TASK_STATUS[task.status]} />
            </summary>
            <div className="space-y-2 px-3 pb-3 pl-9 text-sm">
              {task.status_reason && <p className="text-muted">{task.status_reason}</p>}
              <p className="text-[12px] text-faint">
                {TOOL_LABELS[task.tool_name]} with {formatArgs(task.arguments)}
              </p>
              {task.result?.output && (
                <div>
                  {task.result.mocked && (
                    <p className="mb-1 text-[12px] font-medium text-decide-ink">Simulated data, not from a real service</p>
                  )}
                  <pre className="max-h-56 overflow-auto rounded-lg bg-sunk p-2.5 text-[12px] leading-relaxed text-muted">
                    {JSON.stringify(task.result.output, null, 2)}
                  </pre>
                </div>
              )}
              {task.result?.error && <p className="text-fail">{task.result.error.message}</p>}
              {!task.result && !task.status_reason && <p className="text-faint">No result yet.</p>}
            </div>
          </details>
        </li>
      ))}
    </ul>
  );
}

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  return entries.length ? entries.map(([k, v]) => `${k}: ${String(v)}`).join(", ") : "no arguments";
}
