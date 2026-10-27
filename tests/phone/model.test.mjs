// Design 0025 §3 and §5: the phone app's logic that needs no browser. The stream is live while connected,
// reconnecting while a drop is under thirty seconds old (with the pause's age and the next try), offline after; the
// header says which in a class of its own; Now's model line says what the model does and how fast, the machine is four
// gauges, what waits is counted across OpenCode's asks, the marks and Clank's questions, and the offline screen's
// summary holds names and numbers only. A screen's absent parts are left out, never drawn as the word null.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allSessions, clockText, lastKnown, linkBadge, machineGauges, modelLine, present, streamState, waitingCount, workingRows,
} from "../../clank/components/remote/page/model.mjs";

const NOW = {
  model: { status: "ready", preset: "frontier-262k", title: "frontier 262K" },
  agent: { state: "running", requests: [{ phase: "answering", tokens: 41280, per_second: 75.2, seconds: 372 }], last: null },
  machine: { cpu: 18.4, memory_used: 31 * 1073741824, memory_total: 64 * 1073741824,
             gpu: { use: 94, memory_used: 21.4 * 1073741824, memory_total: 24 * 1073741824 } },
  workspaces: [
    { name: "paper", state: "running", servers: [
      { port: 4096, sessions: [{ id: "s1", title: "Lemma 3", status: "busy", updated: 20 }, { id: "s2", title: "notes", status: "idle", updated: 10 }],
        permissions: [{ id: "per_1" }], questions: [] },
    ] },
    { name: "survey", state: "running", servers: [{ port: 4096, sessions: [{ id: "s3", title: "planning", status: "busy", updated: 30 }], permissions: [], questions: [{ id: "q1" }] }] },
  ],
  questions: [{ id: "q-1", title: "Use the cloud in paper?", options: [] }],
  marks: [],
};

test("the stream is live, then reconnecting with the pause's age, then offline after thirty seconds", () => {
  assert.deepEqual(streamState({ connected: true }, 1000), { state: "live", pausedSeconds: 0, tries: 0, nextTryIn: 0 });
  const dropped = { connected: false, failedSince: 100_000, tries: 2 };
  const young = streamState(dropped, 114_000);
  assert.equal(young.state, "reconnecting");
  assert.equal(young.pausedSeconds, 14);
  assert.equal(young.nextTryIn, 1, "the next try comes on the fives");
  const old = streamState(dropped, 131_000);
  assert.equal(old.state, "offline");
  assert.equal(old.pausedSeconds, 31);
  assert.equal(old.tries, 2);
  assert.equal(clockText(14), "0:14");
  assert.equal(clockText(3723), "1:02:03");
});

test("the header says the stream's state in a class of its own, apart from a session's LIVE tag and the offline screen", () => {
  // Its class was the state's bare name: "live" took the LIVE tag's look (a green block in place of "● live") and
  // "offline" the offline screen's (2026-10-27).
  assert.deepEqual(linkBadge(streamState({ connected: true }, 1000)), { kind: "link-live", words: "● live" });
  const young = streamState({ connected: false, failedSince: 100_000, tries: 2 }, 114_000);
  assert.deepEqual(linkBadge(young), { kind: "link-reconnecting", words: "● reconnecting 0:14" });
  const old = streamState({ connected: false, failedSince: 100_000, tries: 2 }, 131_000);
  assert.deepEqual(linkBadge(old), { kind: "link-offline", words: "● offline" });
});

test("a screen's absent parts are left out, never drawn as the word null", () => {
  // The DOM draws a null handed to replaceChildren as the text "null": it stood at the top of every tab while the
  // stream was live, where the paused line is absent (2026-10-27; app.js's fill() leaves them out through present()).
  const paused = null;
  assert.deepEqual(present([paused, "Now", undefined, false, "Flows"]), ["Now", "Flows"]);
  assert.deepEqual(present([]), []);
});

test("the model's line says what it does, how fast and for how long", () => {
  const line = modelLine(NOW);
  assert.equal(line.title, "frontier 262K");
  assert.equal(line.ready, true);
  assert.equal(line.doing, "writing");
  assert.equal(line.speed, "75 tok/s");
  assert.equal(line.detail, "41,280 tok · 372 s");
  const idle = modelLine({ ...NOW, agent: { state: "running", requests: [], last: { per_second: 62 } } });
  assert.equal(idle.doing, "idle");
  assert.equal(idle.speed, "last 62 tok/s");
  const none = modelLine({ model: { status: "stopped" }, agent: { state: "stopped", requests: [] } });
  assert.equal(none.title, "no model");
  assert.equal(none.doing, "gateway stopped");
});

test("the machine is four gauges, those it reports", () => {
  const gauges = machineGauges(NOW.machine);
  assert.deepEqual(gauges.map((g) => g.label), ["GPU", "VRAM", "CPU", "RAM"]);
  assert.equal(gauges[0].text, "94%");
  assert.equal(gauges[1].text, "21.4 GB");
  assert.equal(gauges[3].text, "31 GB");
  assert.ok(gauges[1].fraction > 0.89 && gauges[1].fraction < 0.9);
  assert.deepEqual(machineGauges(null), []);
  assert.deepEqual(machineGauges({ cpu: 5, memory_used: 0, memory_total: 0 }).map((g) => g.label), ["CPU"]);
});

test("what waits is counted across the asks, the marks and Clank's questions; what works is listed newest first", () => {
  assert.equal(waitingCount(NOW), 3);
  assert.deepEqual(workingRows(NOW).map((s) => s.id), ["s3", "s1"]);
  assert.deepEqual(allSessions(NOW).map((s) => [s.id, s.workspace, s.port]), [["s3", "survey", 4096], ["s1", "paper", 4096], ["s2", "paper", 4096]]);
});

test("the offline screen's summary holds names and numbers only", () => {
  const kept = lastKnown(NOW, 5_000);
  assert.deepEqual(kept, { at: 5_000, model: "frontier 262K · ready", waiting: 3, working: ["survey · planning", "paper · Lemma 3"] });
  assert.equal(JSON.stringify(kept).includes("per_1"), false, "no id of an ask, no text of a message");
});
