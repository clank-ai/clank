// Design 0021 §3: the model's readout in VS Code. The status bar says the speed, the context used of the window and the
// phase ("63 tok/s · 161K/262K · thinking"), and with no session yet the model and its state. The panel's rows: the
// model and its speed options; writing speed (live while it writes, else the last step's), the prompt's reading speed
// for the last step, the drafted tokens accepted, and the recent steps as a small graph; what it does now and for how
// long (a tool or a call by its name); the context used of the window with the compaction line and the cache's share,
// part by part as a bar whose free room is the rest of the window; how much is attended exactly on the GPU and how much
// retrieved; whether the engine holds this session's conversation; the GPU's memory and use. A part the service could
// not read says so, never a number.

import assert from "node:assert/strict";
import { test } from "node:test";

import { footLine, type Readout, panelRows, sparkline, statusText, tokens } from "../src/core/readout";

const WRITING: Readout = {
  folder: "D:\\work\\paper",
  workspace: "paper",
  session: { id: "ses_1", title: "the residuals" },
  now: {
    state: "thinking",
    phase: "thinking",
    working: true,
    seconds: 12.4,
    call: null,
    writing: null,
    prompt: { first_ms: 3200, reading: false, tokens: 161000, cached: 160000, of: "the previous step" },
    speed: { now: 63.2, steps: [41, 55, 60, 63.2] },
  },
  context: {
    window: 262144,
    line: 245760,
    used: 161000,
    cache_share: 0.9938,
    gpu: { device: "gpu", exact: 57344, stored: 161000, attended: 57344, elsewhere: 103656 },
    holder: { this: true, subagent: false, taken: false, lost: false },
    parts: {
      tokens: 160000,
      parts: [
        { part: "system", label: "system prompt", tokens: 4000, share: 0.025 },
        { part: "tools", label: "tool definitions", tokens: 9000, share: 0.056 },
        { part: "results", label: "tool results", tokens: 87000, share: 0.544 },
        { part: "text", label: "the model's text", tokens: 60000, share: 0.375 },
      ],
    },
  },
  slot: {
    status: "ready",
    preset: "frontier-262k-fast",
    title: "frontier 262K fast (trial)",
    speed_options: { "spec.draft_tokens": 4, cuda_graphs: true },
  },
  gpu: { name: "NVIDIA GeForce RTX 5080", use: 91, memory_used: 15.1 * 2 ** 30, memory_total: 16 * 2 ** 30 },
  drafts: { tokens: 2178, drafted: 2433, accepted: 1368, share: 0.562 },
};

test("tokens are written as people read them", () => {
  assert.equal(tokens(161000), "161K");
  assert.equal(tokens(262144), "262K");
  assert.equal(tokens(1536), "1.5K");
  assert.equal(tokens(950), "950");
  assert.equal(tokens(null), "?");
});

test("the speed graph scales the recent steps between the lowest and highest bar", () => {
  assert.equal(sparkline([0, 10, 20, 40]), "▁▂▄█");
  assert.equal(sparkline([30, 30]), "▄▄", "steps all alike: a level line");
  assert.equal(sparkline([]), "");
  assert.equal(sparkline([1, 2, 3, 4, 5], 3), "▁▄█", "only the newest that fit");
});

test("the status bar says the speed, the context used of the window and the phase", () => {
  assert.equal(statusText(WRITING), "$(pulse) 63 tok/s · 161K/262K · thinking");
  const idle = { ...WRITING, now: { ...WRITING.now!, state: "idle", phase: "idle", working: false, speed: { now: 58, steps: [] } } };
  assert.equal(statusText(idle), "$(pulse) last 58 tok/s · 161K/262K · idle");
  assert.equal(statusText({ ...WRITING, session: null, now: null, context: null }), "$(pulse) frontier 262K fast (trial) · ready");
  assert.equal(statusText(undefined), "$(pulse) Clank: no readout");
});

test("the panel shows the model, its speed, what it does now, the context part by part, and the machine", () => {
  const rows = panelRows(WRITING);
  assert.equal(rows.title, "frontier 262K fast (trial) · ready · 4 drafted tokens a step · CUDA graphs on");
  assert.equal(rows.speed, "writing 63 tok/s · drafts 56% accepted");
  assert.equal(rows.graph, sparkline([41, 55, 60, 63.2]));
  assert.equal(rows.now, "thinking · 12 s");
  assert.equal(rows.context, "161K of 262K used (61%) · compaction at 246K · 99% read from the cache");
  assert.deepEqual(
    rows.bar.map((segment) => [segment.label, segment.tokens]),
    [
      ["tool results", 87000],
      ["the model's text", 60000],
      ["tool definitions", 9000],
      ["system prompt", 4000],
      ["free", 262144 - 161000],
    ],
  );
  assert.equal(rows.exact, "57K attended exactly on the GPU; 104K retrieved from system memory");
  assert.equal(rows.engine, "the engine holds this session's conversation");
  assert.equal(rows.machine, "GPU 15.1 of 16.0 GB · 91% busy");
});

test("the reading speed is the last step's, once its prompt was read", () => {
  const ended = {
    ...WRITING,
    now: {
      ...WRITING.now!,
      state: "idle",
      phase: "idle",
      working: false,
      prompt: { first_ms: 2000, reading: false, tokens: 162000, cached: 160000, of: "the last step" },
    },
  };
  assert.equal(panelRows(ended).speed, "last step 63 tok/s · read 1,000 tok/s · drafts 56% accepted");
});

test("the jobs running in the folder's workspace show with how long each has run", () => {
  const jobs = [
    { job: 3, title: "sweep", state: "running", seconds: 754 },
    { job: 4, title: "anneal", state: "starting", seconds: 2 },
  ];
  assert.equal(panelRows({ ...WRITING, jobs }).jobs, "jobs: 3 sweep (12 min) · 4 anneal (starting)");
  assert.equal(panelRows({ ...WRITING, jobs: [] }).jobs, "");
  assert.equal(panelRows(WRITING).jobs, "", "a service from before jobs says none");
});

test("a prompt read mostly from the cache says how few tokens were new, not a speed of them", () => {
  const cached = {
    ...WRITING,
    now: {
      ...WRITING.now!,
      state: "idle",
      phase: "idle",
      working: false,
      prompt: { first_ms: 2300, reading: false, tokens: 14200, cached: 14004, of: "the last step" },
    },
  };
  assert.equal(panelRows(cached).speed, "last step 63 tok/s · read 196 new tokens in 2.3 s · drafts 56% accepted");
});

test("the bar leaves out the parts that hold nothing", () => {
  const empty = { part: "loop", label: "loop text", tokens: 0, share: 0 };
  const context = { ...WRITING.context!, parts: { ...WRITING.context!.parts!, parts: [...WRITING.context!.parts!.parts, empty] } };
  const labels = panelRows({ ...WRITING, context }).bar.map((segment) => segment.label);
  assert.ok(!labels.includes("loop text"));
  assert.ok(labels.includes("free"));
});

test("a tool or a call is named, and an engine holding another conversation is said with its cost", () => {
  const tool = { ...WRITING.now!, state: "tool", phase: "running a tool", call: { tool: "bash", title: "", input: "" } };
  assert.equal(panelRows({ ...WRITING, now: tool }).now, "running a tool: bash · 12 s");
  const call = { ...WRITING.now!, state: "writing", phase: "writing a call", writing: { tool: "edit", arguments: "" } };
  assert.equal(panelRows({ ...WRITING, now: call }).now, "writing a call: edit · 12 s");
  const taken = { ...WRITING.context!, holder: { this: false, subagent: false, taken: true, lost: false } };
  assert.equal(
    panelRows({ ...WRITING, context: taken }).engine,
    "the engine holds another conversation: this session's next step reads its 161K again",
  );
});

test("parts the service could not read say so, never a number", () => {
  const rows = panelRows({ ...WRITING, session: null, now: null, context: null, gpu: null, drafts: null });
  assert.equal(rows.speed, "no session of this folder yet");
  assert.equal(rows.now, "");
  assert.equal(rows.context, "the context shows once the agent has answered");
  assert.deepEqual(rows.bar, []);
  assert.equal(rows.machine, "the GPU's meters are not read");
});

test("the agent panel's foot says the speed, the context used of the window, the drafts and the GPU in one line", () => {
  assert.deepEqual(footLine(WRITING), {
    speed: "63 tok/s", used: "161K", window: "262K", share: 161000 / 262144, drafts: "drafts 56 %",
    gpu: "GPU 15.1 / 16.0 GB", model: "frontier 262K fast (trial)", phase: "Thinking",
  });
});
