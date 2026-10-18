import type { Scheduler } from "./engine";

/**
 * A scheduler with its own clock that only moves when you call `runAll`.
 * Used to pre-compute seeded history runs instantly, with realistic timestamps.
 */
export class VirtualScheduler implements Scheduler {
  private queue: { at: number; seq: number; fn: () => void }[] = [];
  private seq = 0;

  constructor(private time: number) {}

  now(): number {
    return this.time;
  }

  setTimeout(fn: () => void, ms: number): unknown {
    const entry = { at: this.time + ms, seq: this.seq++, fn };
    this.queue.push(entry);
    return entry;
  }

  clearTimeout(handle: unknown): void {
    this.queue = this.queue.filter((e) => e !== handle);
  }

  /** Runs every scheduled callback (including ones they schedule) in time order. */
  runAll(): void {
    while (this.queue.length) {
      this.queue.sort((a, b) => a.at - b.at || a.seq - b.seq);
      const next = this.queue.shift()!;
      this.time = next.at;
      next.fn();
    }
  }
}
