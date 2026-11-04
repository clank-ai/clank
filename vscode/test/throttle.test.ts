// Design 0021 §3: the agent panel asks for the model's readout at most once a second, never twice at once, however
// many snapshots the conversation's stream sends (one per streamed chunk in a long session sent a readout request
// each), and the last call is never lost: the newest readout is read once the second is up.

import assert from "node:assert/strict";
import { test } from "node:test";

import { Throttle, type Timer } from "../src/core/throttle";

function clock(): { now: () => number; timer: Timer; advance: (ms: number) => Promise<void> } {
  let time = 0;
  const due: Array<{ at: number; run: () => void; gone: boolean }> = [];
  const timer: Timer = (run, ms) => {
    const entry = { at: time + ms, run, gone: false };
    due.push(entry);
    return { cancel: () => { entry.gone = true; } };
  };
  const advance = async (ms: number): Promise<void> => {
    time += ms;
    for (const entry of due.filter((each) => !each.gone && each.at <= time)) {
      entry.gone = true;
      entry.run();
    }
    await new Promise((settled) => setImmediate(settled));
  };
  return { now: () => time, timer, advance };
}

test("calls within a second are one run once the second is up, and two never run at once", async () => {
  const { now, timer, advance } = clock();
  let runs = 0;
  let open = 0;
  let most = 0;
  const throttle = new Throttle(1000, async () => {
    runs += 1;
    open += 1;
    most = Math.max(most, open);
    await new Promise((settled) => setImmediate(settled));
    open -= 1;
  }, now, timer);
  throttle.run();
  await advance(0);
  assert.equal(runs, 1, "the first runs at once");
  for (let chunk = 0; chunk < 200; chunk += 1) {
    throttle.run(); // a snapshot per streamed chunk
  }
  await advance(500);
  assert.equal(runs, 1, "not before the second is up");
  await advance(500);
  assert.equal(runs, 2, "the calls meanwhile are one run, the newest state read");
  await advance(5000);
  assert.equal(runs, 2, "nothing more without a call");
  assert.equal(most, 1, "never two at once");
});

test("a call while the task runs is run once it ends, and a disposed throttle runs nothing more", async () => {
  const { now, timer, advance } = clock();
  let finish: (() => void) | undefined;
  let runs = 0;
  const throttle = new Throttle(10, () => {
    runs += 1;
    return new Promise<void>((settled) => { finish = settled; });
  }, now, timer);
  throttle.run();
  throttle.run();
  assert.equal(runs, 1);
  await advance(50);
  assert.equal(runs, 1, "it still runs: the second waits for it");
  finish?.();
  await advance(0);
  await advance(10);
  assert.equal(runs, 2);
  throttle.run();
  throttle.dispose();
  finish?.();
  await advance(100);
  assert.equal(runs, 2, "disposed: the waiting call is forgotten");
});
