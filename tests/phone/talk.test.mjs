// Design 0025 §7: a session's talk on the phone, built from the conversation stream's events as the extension's client
// builds it (design 0023 §3). A snapshot replaces the conversation and its version; a message, a part, a delta and a
// removal change one thing each, a delta appending to its part's text as the model writes; the status says whether the
// session works; the waits replace the waits; the readout is kept for the header; `session` names the session to open
// instead. A message sent shows at once as pending, settles when its message arrives from the mirror, and is given
// back when the send fails. The items drawn are the conversation's (the owner's words, the model's text, its thinking
// with its length, each call in one line, a failed step, a compaction), then the pending ones; the live item is the
// last of the message the model writes, while the session works.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  applyTalk, callLine, emptyTalk, failedTalk, liveIndex, sentTalk, talkItems,
} from "../../clank/components/remote/page/model.mjs";

const SNAPSHOT = {
  folder: "C:/work/paper", workspace: "paper",
  session: { id: "ses_1", title: "A plan", port: 4096, busy: false },
  messages: [
    { info: { id: "msg_1", role: "user", created: 100 }, parts: [{ id: "prt_1", type: "text", text: "Plot it." }] },
    { info: { id: "msg_2", role: "assistant", created: 200 }, parts: [
      { id: "prt_2a", type: "reasoning", text: "Thinking." }, { id: "prt_2b", type: "text", text: "The plot" },
    ] },
  ],
  next: "", waiting: { permissions: [], questions: [] }, version: 7,
};

function withSnapshot() {
  return applyTalk(emptyTalk(), "snapshot", SNAPSHOT, 7);
}

test("a snapshot replaces the conversation and its version", () => {
  const talk = withSnapshot();
  assert.equal(talk.version, 7);
  assert.equal(talk.conversation.session.id, "ses_1");
  assert.deepEqual(talk.conversation.messages.map((m) => m.info.id), ["msg_1", "msg_2"]);
  assert.equal("version" in talk.conversation, false, "the version is the state's, not the conversation's");
});

test("a message, a part, a delta and a removal change one thing each, in the message's order", () => {
  let talk = withSnapshot();
  talk = applyTalk(talk, "message", { type: "message", message: { id: "msg_3", role: "assistant", created: 300 } }, 8);
  talk = applyTalk(talk, "delta", { type: "delta", message: "msg_3", part: "prt_3b", text: "The " }, 9);
  talk = applyTalk(talk, "delta", { type: "delta", message: "msg_3", part: "prt_3b", text: "fit" }, 10);
  talk = applyTalk(talk, "part", { type: "part", message: "msg_3", part: { id: "prt_3a", type: "reasoning", text: "Hm." } }, 11);
  assert.equal(talk.version, 11);
  const third = talk.conversation.messages[2];
  assert.equal(third.info.id, "msg_3");
  assert.deepEqual(third.parts.map((p) => [p.id, p.text]), [["prt_3a", "Hm."], ["prt_3b", "The fit"]], "parts by id");
  talk = applyTalk(talk, "part", { type: "part", message: "msg_3", part: { id: "prt_3b", type: "text", text: "The fit is good." } }, 12);
  assert.equal(talk.conversation.messages[2].parts[1].text, "The fit is good.", "a part line replaces the part");
  talk = applyTalk(talk, "removed", { type: "removed", message: "msg_3", part: "prt_3a" }, 13);
  assert.deepEqual(talk.conversation.messages[2].parts.map((p) => p.id), ["prt_3b"]);
  talk = applyTalk(talk, "removed", { type: "removed", message: "msg_3" }, 14);
  assert.deepEqual(talk.conversation.messages.map((m) => m.info.id), ["msg_1", "msg_2"]);
  talk = applyTalk(talk, "message", { type: "message", message: { id: "msg_2", role: "assistant", created: 200, completed: 250 } }, 15);
  assert.equal(talk.conversation.messages[1].info.completed, 250, "a message's info updated in place");
  assert.equal(talk.version, 15);
});

test("the status, the waits, the readout and the session to open instead", () => {
  let talk = withSnapshot();
  talk = applyTalk(talk, "status", { type: "status", busy: true, status: "busy" }, 8);
  assert.equal(talk.conversation.session.busy, true);
  const permission = { id: "per_1", session: "ses_1", permission: "bash", patterns: ["rm"], metadata: {} };
  talk = applyTalk(talk, "waiting", { type: "waiting", waiting: { permissions: [permission], questions: [] } }, 9);
  assert.deepEqual(talk.conversation.waiting.permissions, [permission]);
  talk = applyTalk(talk, "readout", { type: "readout", readout: { slot: { title: "frontier" }, now: { phase: "answering" } } });
  assert.equal(talk.readout.now.phase, "answering");
  assert.equal(talk.version, 9, "a readout has no version");
  talk = applyTalk(talk, "session", { id: "ses_2" });
  assert.equal(talk.reconnect, "ses_2");
  talk = applyTalk(talk, "connected", {});
  assert.equal(talk.reconnect, "ses_2", "nothing else changes it until the client reopens");
  assert.equal(applyTalk(emptyTalk(), "status", { busy: true }, 3).version, 3, "a change before any snapshot moves the version only");
});

test("a message sent shows at once, settles when its message arrives, and is given back when the send fails", () => {
  let talk = withSnapshot();
  talk = sentTalk(talk, "p1", "Use a log scale.");
  const items = talkItems(talk);
  assert.deepEqual(items.at(-1), { kind: "owner", id: "p1", message: "p1", text: "Use a log scale.", pending: true });
  assert.equal(items.filter((each) => each.kind === "owner").length, 2);
  talk = applyTalk(talk, "message", { type: "message", message: { id: "msg_3", role: "user", created: 300 } }, 8);
  assert.equal(talk.pending.length, 1, "its text is not there yet");
  talk = applyTalk(talk, "part", { type: "part", message: "msg_3", part: { id: "prt_3", type: "text", text: "Use a log scale." } }, 9);
  assert.deepEqual(talk.pending, [], "the owner's message arrived from the mirror");
  assert.deepEqual(talkItems(talk).filter((each) => each.kind === "owner").map((each) => each.id), ["msg_1", "msg_3"]);
  talk = sentTalk(talk, "p2", "And export it.");
  const [back, after] = failedTalk(talk, "p2");
  assert.equal(back, "And export it.");
  assert.deepEqual(after.pending, []);
  const snapshot = applyTalk(sentTalk(after, "p3", "Plot it."), "snapshot", SNAPSHOT, 7);
  assert.deepEqual(snapshot.pending, [], "a snapshot holding the text ends the pending message too");
});

test("the items are the owner's words, the text, the thinking with its length, each call in one line, a failed step and a compaction", () => {
  const messages = [
    { info: { id: "msg_1", role: "user", created: 100 }, parts: [
      { id: "prt_1a", type: "text", text: "Plot it." }, { id: "prt_1b", type: "text", text: "<system>", synthetic: true },
    ] },
    { info: { id: "msg_2", role: "assistant", created: 200 }, parts: [
      { id: "prt_2a", type: "reasoning", text: "Thinking.", length: 1188 },
      { id: "prt_2b", type: "tool", tool: "clank_run_job", status: "completed", title: "", input: '{"command": "python plot.py"}',
        output: "job 3 started", time: { start: 1000, end: 4200 } },
      { id: "prt_2c", type: "tool", tool: "read", status: "running", input: '{"filePath": "paper.tex", "limit": 20', output: "" },
      { id: "prt_2d", type: "text", text: "The plot" },
    ] },
    { info: { id: "msg_3", role: "user", created: 300 }, parts: [
      { id: "prt_3", type: "text", text: "Job 3 (python plot.py) ended after 2 s. The last lines of its log, out.log:\n…" },
    ] },
    { info: { id: "msg_4", role: "assistant", created: 400, summary: true }, parts: [{ id: "prt_4", type: "text", text: "A summary." }] },
    { info: { id: "msg_5", role: "assistant", created: 500, error: "the engine refused" }, parts: [{ id: "prt_5", type: "text", text: "" }] },
  ];
  const items = talkItems({ ...emptyTalk(), conversation: { ...SNAPSHOT, messages } });
  assert.deepEqual(items.map((each) => each.kind), ["owner", "thinking", "call", "call", "text", "notice", "compaction", "error"]);
  assert.equal(items[0].text, "Plot it.", "the synthetic part left out");
  assert.equal(items[1].length, 1188);
  assert.deepEqual([items[2].line, items[2].status, items[2].chars, items[2].seconds], ["run_job: python plot.py", "completed", 13, 3]);
  assert.deepEqual([items[3].line, items[3].status, items[3].seconds], ["read: paper.tex", "running", null], "an input cut past the limit still names the file");
  assert.equal(items[5].title, "Job 3 ended");
  assert.equal(items[5].detail, "python plot.py · ended after 2 s");
  assert.equal(items[7].text, "the engine refused");
  assert.equal(callLine("bash", { command: "ls -la\ncd .." }, ""), "bash: ls -la", "the first line of what it was given");
  assert.equal(callLine("clank_show_files", {}, "the figure"), "show_files: the figure", "the title first");
});

test("the live item is the last of the model's newest message while the session works", () => {
  let talk = withSnapshot();
  assert.equal(liveIndex(talk), -1, "idle: nothing is live");
  talk = applyTalk(talk, "status", { busy: true }, 8);
  const items = talkItems(talk);
  assert.equal(liveIndex(talk, items), items.length - 1);
  assert.equal(items[liveIndex(talk, items)].id, "prt_2b");
  talk = applyTalk(talk, "message", { message: { id: "msg_3", role: "user", created: 300 } }, 9);
  assert.equal(liveIndex(talk), -1, "the owner's message is newest: the model has not begun");
  talk = applyTalk(talk, "message", { message: { id: "msg_4", role: "assistant", created: 400 } }, 10);
  assert.equal(liveIndex(talk), -1, "a message with no part yet: nothing to mark");
  talk = applyTalk(talk, "delta", { message: "msg_4", part: "prt_4", text: "On " }, 11);
  assert.equal(talkItems(talk)[liveIndex(talk)].text, "On ");
  assert.equal(liveIndex(sentTalk(talk, "p1", "Wait.")), talkItems(talk).length - 1, "a pending message is never the live one");
});
