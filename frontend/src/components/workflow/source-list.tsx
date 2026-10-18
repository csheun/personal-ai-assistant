import { ExternalLink } from "lucide-react";

import type { Citation } from "@/lib/api/types";

/** Numbered links matching the [n] markers in a summary. */
export function SourceList({ sources, compact = false }: { sources: Citation[]; compact?: boolean }) {
  if (sources.length === 0) return null;
  return (
    <div className={compact ? "mt-2" : "mt-3 border-t border-ok/20 pt-3"}>
      <h4 className="mb-1 text-[12px] font-semibold text-muted">Sources</h4>
      <ol className="space-y-1">
        {sources.map((s) => (
          <li key={s.ref} className="flex min-w-0 gap-1.5 text-[13px]">
            <span className="tabular shrink-0 text-faint">[{s.ref}]</span>
            <a
              href={s.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="inline-flex min-w-0 items-center gap-1 text-accent underline-offset-2 hover:underline"
            >
              <span className="truncate">{compact ? hostname(s.url) : s.title || hostname(s.url)}</span>
              <ExternalLink className="size-3 shrink-0" aria-hidden />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
