"use client";

import { useEffect, useState } from "react";

/**
 * Current time, re-rendering every `intervalMs` while `active`.
 * Null until mounted, so prerendered HTML never depends on the clock.
 */
export function useNow(active: boolean, intervalMs = 100): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const frame = requestAnimationFrame(tick);
    const id = active ? setInterval(tick, intervalMs) : undefined;
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(id);
    };
  }, [active, intervalMs]);
  return now;
}
