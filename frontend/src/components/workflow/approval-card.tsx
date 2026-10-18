"use client";

import { Check, Hand, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ApprovalDecision, ApprovalRequest } from "@/lib/api/types";

export function ApprovalCard({
  approval,
  onResolve,
}: {
  approval: ApprovalRequest;
  onResolve: (id: string, decision: ApprovalDecision) => void;
}) {
  const [submitted, setSubmitted] = useState<ApprovalDecision | null>(null);

  const decide = (decision: ApprovalDecision) => {
    setSubmitted(decision);
    onResolve(approval.id, decision);
  };

  return (
    <section
      id={`approval-${approval.id}`}
      aria-labelledby={`approval-title-${approval.id}`}
      className="motion-safe:animate-rise rounded-xl border border-decide/50 bg-decide-soft p-4"
    >
      <div className="flex items-start gap-2.5">
        <Hand className="mt-0.5 size-5 shrink-0 text-decide-ink" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 id={`approval-title-${approval.id}`} className="font-semibold text-decide-ink">
            Send this to Telegram?
          </h3>
          <p className="text-sm text-decide-ink/80">{approval.action}. Nothing is sent until you approve.</p>
        </div>
      </div>

      <figure className="mt-3 rounded-lg bg-surface p-3 ring-1 ring-line">
        <figcaption className="mb-1 text-[12px] font-medium text-muted">To {approval.preview.destination}</figcaption>
        <blockquote className="whitespace-pre-wrap text-sm">{approval.preview.body}</blockquote>
      </figure>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="decide" onClick={() => decide("approve")} disabled={submitted !== null}>
          <Check className="size-4" aria-hidden />
          {submitted === "approve" ? "Approving…" : "Approve and send"}
        </Button>
        <Button onClick={() => decide("reject")} disabled={submitted !== null}>
          <X className="size-4" aria-hidden />
          {submitted === "reject" ? "Rejecting…" : "Reject"}
        </Button>
        <span className="text-[12px] text-decide-ink/80">Mock mode: approving won&apos;t send a real message.</span>
      </div>
    </section>
  );
}
