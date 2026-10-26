// Design 0025 §6: the Flows tab's logic that needs no browser. The filters keep the flows by state (Running takes
// what runs, is paused, is queued or is being built; Waits what waits for you; Ended what is done or stopped); a run's
// controls follow its state (Pause and Stop while it runs, Resume and Stop while paused, Run otherwise); each box has
// a glyph for its state, a gate its own.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boxGlyph, flowFilter, runControls } from "../../clank/components/remote/page/model.mjs";

const ROWS = [
  { id: "a/one", state: "running" },
  { id: "a/two", state: "waits" },
  { id: "a/three", state: "done" },
  { id: "a/four", state: "stopped" },
  { id: "a/five", state: "never" },
  { id: "a/six", state: "building" },
  { id: "a/seven", state: "paused" },
  { id: "a/eight", state: "queued" },
];

test("the filters keep the flows by state, and All keeps every one", () => {
  const ids = (which) => flowFilter(ROWS, which).map((row) => row.id);
  assert.deepEqual(ids("all"), ROWS.map((row) => row.id));
  assert.deepEqual(ids("running"), ["a/one", "a/six", "a/seven", "a/eight"]);
  assert.deepEqual(ids("waits"), ["a/two"]);
  assert.deepEqual(ids("ended"), ["a/three", "a/four"]);
  assert.deepEqual(ids("nonsense"), ROWS.map((row) => row.id), "an unknown filter keeps every flow");
});

test("a run's controls follow its state", () => {
  assert.deepEqual(runControls(null), ["run"]);
  assert.deepEqual(runControls({ status: "running", paused: false }), ["pause", "stop"]);
  assert.deepEqual(runControls({ status: "running", paused: true }), ["resume", "stop"]);
  assert.deepEqual(runControls({ status: "queued", paused: false }), ["stop"]);
  assert.deepEqual(runControls({ status: "done", paused: false }), ["run"]);
  assert.deepEqual(runControls({ status: "stopped", paused: false }), ["run"]);
});

test("each box has a glyph for its state, a gate its own while it waits", () => {
  assert.equal(boxGlyph({ state: "waiting", type: "task" }), "○");
  assert.equal(boxGlyph({ state: "running", type: "task" }), "●");
  assert.equal(boxGlyph({ state: "done", type: "gate" }), "✓");
  assert.equal(boxGlyph({ state: "failed", type: "verify" }), "✗");
  assert.equal(boxGlyph({ state: "waiting", type: "gate" }), "◇");
  assert.equal(boxGlyph({ state: "stale", type: "task" }), "!");
  assert.equal(boxGlyph({ state: "skipped", type: "task" }), "!");
  assert.equal(boxGlyph({ state: "proposed", type: "task" }), "?");
});
