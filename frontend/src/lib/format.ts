/** 850 → "0.9s", 12_400 → "12.4s", 75_000 → "1m 15s". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || ms < 0) return "–";
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

/** Short relative date for lists: "Just now", "5 min ago", "Yesterday", "Oct 14". */
export function formatRelative(iso: string, now: number): string {
  const then = Date.parse(iso);
  const diff = now - then;
  if (diff < 60_000) return "Just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} min ago`;
  const startOfToday = new Date(now);
  startOfToday.setHours(0, 0, 0, 0);
  if (then >= startOfToday.getTime()) {
    return new Date(then).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  if (then >= startOfToday.getTime() - 86_400_000) return "Yesterday";
  return new Date(then).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
