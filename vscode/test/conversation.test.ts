// Design 0021 §4: the agent panel's conversation, drawn from a page of the session's messages in the Monitor's shape.
// The owner's messages (OpenCode's own synthetic parts left out); the model's text, its thinking (folded when drawn) and
// each tool call with its state and a one-line summary (Clank's tools named without their server's prefix); a figure
// the agent looked at or showed, inline, as a path in the folder; an artifact it made, as a card with its name and
// version; a step that failed, and a compaction, said. Math in the model's text is set aside before Markdown reads it
// (so its underscores stay math), each piece drawn by KaTeX in its place. What waits in the session (permissions and
// questions) comes as items too, last.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type Conversation,
  callSummary,
  conversationItems,
  type PageMessage,
  splitMath,
  waitingItems,
} from "../src/core/conversation";

function step(id: string, parts: PageMessage["parts"], info: Partial<PageMessage["info"]> = {}): PageMessage {
  return { info: { id, role: "assistant", finish: "stop", error: "", ...info }, parts };
}

const PAGE: PageMessage[] = [
  {
    info: { id: "msg_1", role: "user" },
    parts: [
      { id: "prt_1", type: "text", text: "Plot the sweep." },
      { id: "prt_2", type: "text", text: "<system-reminder>…</system-reminder>", synthetic: true },
    ],
  },
  step("msg_2", [
    { id: "prt_3", type: "step-start" },
    { id: "prt_4", type: "reasoning", text: "The data is in data/sweep.csv.", length: 31 },
    {
      id: "prt_5", type: "tool", tool: "bash", status: "completed", title: "",
      input: { command: "python3 simulate.py --fast", description: "Run the simulation" }, output: "done\n",
    },
    {
      id: "prt_6", type: "tool", tool: "clank_look_at_figure", status: "completed", title: "",
      input: { path: "/workspace/figures/sweep.png", question: "Are the axes labeled?" }, output: "Yes.",
    },
    { id: "prt_7", type: "step-finish" },
  ], { finish: "tool-calls" }),
  step("msg_3", [
    {
      id: "prt_8", type: "tool", tool: "clank_make_artifact", status: "completed", title: "",
      input: { name: "sweep", title: "Sweep results", kind: "html", files: ["sweep.html"] },
      output: "Artifact Sweep results (sweep), version 2, made: it opens in the owner's VS Code window, beside you.",
    },
    { id: "prt_9", type: "text", text: "The period is $T_0 = 2\\pi\\sqrt{L/g}$; see the chart.", length: 52 },
  ]),
  step("msg_4", [{ id: "prt_10", type: "tool", tool: "read", status: "running", title: "workspace/notes.md", input: {} }], {
    finish: null,
  }),
  step("msg_5", [], { error: "the model's server did not answer", finish: null }),
  step("msg_6", [{ id: "prt_11", type: "text", text: "Summary of the work so far." }], { summary: true }),
];

test("a page becomes the owner's messages, the model's text, thinking and calls, figures and artifact cards", () => {
  const items = conversationItems(PAGE);
  assert.deepEqual(
    items.map((item) => item.kind),
    ["owner", "thinking", "call", "call", "image", "call", "artifact", "text", "call", "error", "compaction"],
  );
  assert.deepEqual(items[0], { kind: "owner", id: "msg_1", text: "Plot the sweep." }, "the synthetic part left out");
  const look = items[4];
  assert.equal(look.kind, "image");
  assert.equal(look.kind === "image" && look.path, "figures/sweep.png", "a path in the folder");
  const card = items[6];
  assert.deepEqual(card, { kind: "artifact", id: "prt_8-artifact", name: "sweep", title: "Sweep results", version: 2 });
  const running = items[8];
  assert.equal(running.kind === "call" && running.status, "running");
  assert.equal(items[9].kind === "error" && items[9].text, "the model's server did not answer");
  assert.equal(new Set(items.map((item) => item.id)).size, items.length, "every item has its own id, for its fold");
});

test("a call is summed up in one line: its tool without Clank's prefix and what it was given", () => {
  const [, , bash, look, , artifact, , , read] = conversationItems(PAGE);
  assert.equal(bash.kind === "call" && bash.summary, "bash: python3 simulate.py --fast");
  assert.equal(look.kind === "call" && look.summary, "look_at_figure: /workspace/figures/sweep.png");
  assert.equal(artifact.kind === "call" && artifact.summary, "make_artifact: sweep");
  assert.equal(read.kind === "call" && read.summary, "read: workspace/notes.md", "OpenCode's own title first");
  assert.equal(callSummary("glob", { pattern: "**/*.tex" }, ""), "glob: **/*.tex");
  assert.equal(callSummary("todowrite", {}, ""), "todowrite");
});

test("a call's input given as JSON text, or cut past the bridge's limit, is still read for its summary and card", () => {
  assert.equal(callSummary("clank_run_job", '{"command": "python3 simulate.py", "title": "Sweep"}', ""), "run_job: python3 simulate.py");
  const cut = '{"name": "pendulum", "title": "Pendulum \\"period\\"", "files": ["pendulum.html", "data/sweep.csv", "data/sim … [912 characters]';
  const [call, card] = conversationItems([{
    info: { id: "msg_9", role: "assistant" },
    parts: [{ id: "prt_9", type: "tool", tool: "clank_make_artifact", status: "completed", title: "", input: cut,
              output: "Artifact Pendulum (pendulum), version 3, made." }],
  }]);  // prettier-ignore
  assert.equal(call.kind === "call" && call.summary, "make_artifact: pendulum");
  assert.deepEqual(card, { kind: "artifact", id: "prt_9-artifact", name: "pendulum", title: 'Pendulum "period"', version: 3 });
  const [shown] = conversationItems([{
    info: { id: "msg_10", role: "assistant" },
    parts: [{ id: "prt_10", type: "tool", tool: "bash", status: "completed", title: "", input: '{"command": "ls"}' }],
  }]);  // prettier-ignore
  assert.equal(shown.kind === "call" && shown.input, '{\n  "command": "ls"\n}', "shown laid out when it is whole");
});

test("math is set aside before Markdown reads the text and drawn in its place", () => {
  const split = splitMath("Let $a_1 = b_2$ and $$\\sum_i x_i$$ hold, with \\(y_k\\) too; it costs $5.");
  assert.equal(split.text, "Let @@MATH0@@ and @@MATH1@@ hold, with @@MATH2@@ too; it costs $5.");
  assert.deepEqual(split.math, [
    { text: "a_1 = b_2", display: false },
    { text: "\\sum_i x_i", display: true },
    { text: "y_k", display: false },
  ]);
});

test("what waits in the session comes as items: each permission with what it asks, each question", () => {
  const waiting: Conversation["waiting"] = {
    permissions: [{ id: "per_1", session: "ses_1", permission: "bash", patterns: ["rm -r out"], metadata: {} }],
    questions: [{ id: "que_1", session: "ses_1", questions: [{ question: "Which plot?", options: [{ label: "Both" }] }] }],
  };
  assert.deepEqual(waitingItems(waiting), [
    { kind: "permission", id: "per_1", permission: "bash", patterns: ["rm -r out"] },
    { kind: "question", id: "que_1", questions: [{ question: "Which plot?", options: [{ label: "Both" }] }] },
  ]);
});
