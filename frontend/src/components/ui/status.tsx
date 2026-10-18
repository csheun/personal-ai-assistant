import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  CircleX,
  Hand,
  LoaderCircle,
  PlayCircle,
  type LucideIcon,
} from "lucide-react";

import type { RunStatus, TaskStatus } from "@/lib/api/types";

type Tone = "neutral" | "active" | "decide" | "ok" | "fail" | "muted";

interface StatusMeta {
  label: string;
  icon: LucideIcon;
  tone: Tone;
  spin?: boolean;
}

export const TASK_STATUS: Record<TaskStatus, StatusMeta> = {
  pending: { label: "Pending", icon: CircleDashed, tone: "neutral" },
  running: { label: "Running", icon: LoaderCircle, tone: "active", spin: true },
  waiting_for_approval: { label: "Needs approval", icon: Hand, tone: "decide" },
  completed: { label: "Completed", icon: CircleCheck, tone: "ok" },
  failed: { label: "Failed", icon: CircleX, tone: "fail" },
  skipped: { label: "Skipped", icon: CircleSlash, tone: "muted" },
  cancelled: { label: "Cancelled", icon: Ban, tone: "muted" },
};

export const RUN_STATUS: Record<RunStatus, StatusMeta> = {
  planned: { label: "Ready to run", icon: PlayCircle, tone: "neutral" },
  running: { label: "Running", icon: LoaderCircle, tone: "active", spin: true },
  waiting_for_approval: { label: "Needs your approval", icon: Hand, tone: "decide" },
  completed: { label: "Completed", icon: CircleCheck, tone: "ok" },
  failed: { label: "Failed", icon: CircleX, tone: "fail" },
  cancelled: { label: "Cancelled", icon: Ban, tone: "muted" },
};

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-muted",
  active: "text-accent",
  decide: "text-decide-ink",
  ok: "text-ok",
  fail: "text-fail",
  muted: "text-faint",
};

const TONE_PILL: Record<Tone, string> = {
  neutral: "bg-sunk text-muted ring-line",
  active: "bg-accent-soft text-accent ring-accent/25",
  decide: "bg-decide-soft text-decide-ink ring-decide/40",
  ok: "bg-ok-soft text-ok ring-ok/25",
  fail: "bg-fail-soft text-fail ring-fail/25",
  muted: "bg-sunk text-faint ring-line",
};

export const toneText = (tone: Tone) => TONE_TEXT[tone];

/** Icon-only indicator; the label is still available to screen readers. */
export function StatusIcon({ meta, className = "size-4" }: { meta: StatusMeta; className?: string }) {
  const Icon = meta.icon;
  return (
    <span className={`inline-flex shrink-0 ${TONE_TEXT[meta.tone]}`} role="img" aria-label={meta.label}>
      <Icon className={`${className} ${meta.spin ? "motion-safe:animate-spin" : ""}`} aria-hidden strokeWidth={2.25} />
    </span>
  );
}

/** Icon plus visible text: never color alone. */
export function StatusPill({ meta, className = "" }: { meta: StatusMeta; className?: string }) {
  const Icon = meta.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[13px] font-medium ring-1 ring-inset ${TONE_PILL[meta.tone]} ${className}`}
    >
      <Icon className={`size-3.5 ${meta.spin ? "motion-safe:animate-spin" : ""}`} aria-hidden strokeWidth={2.5} />
      {meta.label}
    </span>
  );
}
