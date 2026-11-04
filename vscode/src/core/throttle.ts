// A task run at most once a period, never twice at once (the agent panel's readout, design 0021 §3): a call that comes
// too soon, or while the task runs, is kept, and the task runs once more when the period is up, so the newest state is
// read in the end and never more often than the period. Pure but for the timer it is given.

export type Timer = (run: () => void, ms: number) => { cancel(): void };

const realTimer: Timer = (run, ms) => {
  const handle = setTimeout(run, ms);
  return { cancel: () => clearTimeout(handle) };
};

export class Throttle {
  private last = Number.NEGATIVE_INFINITY;
  private running = false;
  private pending = false;
  private waiting: { cancel(): void } | undefined;

  constructor(
    private readonly ms: number,
    private readonly task: () => Promise<void>,
    private readonly now: () => number = Date.now,
    private readonly timer: Timer = realTimer,
  ) {}

  /** Run the task now, or once the period is up; calls meanwhile are one run. */
  run(): void {
    if (this.running || this.waiting) {
      this.pending = true;
      return;
    }
    const wait = this.last + this.ms - this.now();
    if (wait > 0) {
      this.waiting = this.timer(() => {
        this.waiting = undefined;
        this.run();
      }, wait);
      return;
    }
    this.running = true;
    this.pending = false;
    this.last = this.now();
    void this.task()
      .catch(() => undefined) // the task says its own failures; a throttle only paces it
      .finally(() => {
        this.running = false;
        if (this.pending) {
          this.pending = false;
          this.run();
        }
      });
  }

  /** Forget a run waiting for its time. */
  dispose(): void {
    this.waiting?.cancel();
    this.waiting = undefined;
    this.pending = false;
  }
}
