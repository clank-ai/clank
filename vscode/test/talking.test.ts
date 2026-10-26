// Design 0023 §3 and §5: the agent panel's live state, built from the conversation stream's events (pure). A snapshot
// replaces the conversation and its version; a message, a part, a delta and a removal change one thing each, a
// delta appending to its part's text as the model writes; the status says whether the session works; the waits
// replace the waits; the readout is kept for the header and the foot; `session` says which session to open instead.
// A message the owner sends shows at once as pending, is replaced when its message arrives from the mirror, and is
// given back when the send fails. The items drawn are the conversation's, then the pending ones.

import assert from "node:assert/strict";
import { test } from "node:test";

import type { ServerEvent } from "../src/core/events";
import {
  applyEvent,
  emptyTalk,
  failed,
  liveItems,
  sent,
  type Talk,
} from "../src/core/talking";

function event(name: string, data: unknown, id?: number): ServerEvent {
  return { name, id, data };
}

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
}; // prettier-ignore

function withSnapshot(): Talk {
  return applyEvent(emptyTalk(), event("snapshot", SNAPSHOT, 7));
}

test("a snapshot replaces the conversation and its version", () => {
  const talk = withSnapshot();
  assert.equal(talk.version, 7);
  assert.equal(talk.conversation?.session?.id, "ses_1");
  assert.deepEqual(
    talk.conversation?.messages.map((m) => m.info.id),
    ["msg_1", "msg_2"],
  );
  assert.equal(
    "version" in (talk.conversation ?? {}),
    false,
    "the version is the state's, not the conversation's",
  );
});

test("a message, a part, a delta and a removal change one thing each, in the message's order", () => {
  let talk = withSnapshot();
  talk = applyEvent(
    talk,
    event(
      "message",
      {
        type: "message",
        message: { id: "msg_3", role: "assistant", created: 300 },
      },
      8,
    ),
  );
  talk = applyEvent(
    talk,
    event(
      "delta",
      { type: "delta", message: "msg_3", part: "prt_3b", text: "The " },
      9,
    ),
  );
  talk = applyEvent(
    talk,
    event(
      "delta",
      { type: "delta", message: "msg_3", part: "prt_3b", text: "fit" },
      10,
    ),
  );
  talk = applyEvent(
    talk,
    event(
      "part",
      {
        type: "part",
        message: "msg_3",
        part: { id: "prt_3a", type: "reasoning", text: "Hm." },
      },
      11,
    ),
  );
  assert.equal(talk.version, 11);
  const third = talk.conversation?.messages[2];
  assert.equal(third?.info.id, "msg_3");
  assert.deepEqual(
    third?.parts.map((p) => [p.id, p.text]),
    [
      ["prt_3a", "Hm."],
      ["prt_3b", "The fit"],
    ],
    "parts by id",
  );
  talk = applyEvent(
    talk,
    event(
      "part",
      {
        type: "part",
        message: "msg_3",
        part: { id: "prt_3b", type: "text", text: "The fit is good." },
      },
      12,
    ),
  );
  assert.equal(
    talk.conversation?.messages[2].parts[1].text,
    "The fit is good.",
    "a part line replaces the part",
  );
  talk = applyEvent(
    talk,
    event("removed", { type: "removed", message: "msg_3", part: "prt_3a" }, 13),
  );
  assert.deepEqual(
    talk.conversation?.messages[2].parts.map((p) => p.id),
    ["prt_3b"],
  );
  talk = applyEvent(
    talk,
    event("removed", { type: "removed", message: "msg_3" }, 14),
  );
  assert.deepEqual(
    talk.conversation?.messages.map((m) => m.info.id),
    ["msg_1", "msg_2"],
  );
  talk = applyEvent(
    talk,
    event(
      "message",
      {
        type: "message",
        message: {
          id: "msg_2",
          role: "assistant",
          created: 200,
          completed: 250,
        },
      },
      15,
    ),
  );
  assert.equal(
    talk.conversation?.messages[1].info.completed,
    250,
    "a message's info updated in place",
  );
});

test("the status, the waits, the readout and the session to open instead", () => {
  let talk = withSnapshot();
  talk = applyEvent(
    talk,
    event("status", { type: "status", busy: true, status: "busy" }, 8),
  );
  assert.equal(talk.conversation?.session?.busy, true);
  const permission = {
    id: "per_1",
    session: "ses_1",
    permission: "bash",
    patterns: ["rm"],
    metadata: {},
  };
  talk = applyEvent(
    talk,
    event(
      "waiting",
      {
        type: "waiting",
        waiting: { permissions: [permission], questions: [] },
      },
      9,
    ),
  );
  assert.deepEqual(talk.conversation?.waiting.permissions, [permission]);
  talk = applyEvent(
    talk,
    event("readout", {
      type: "readout",
      readout: { slot: { title: "frontier" }, now: { phase: "writing" } },
    }),
  );
  assert.equal(
    (talk.readout as { now: { phase: string } }).now.phase,
    "writing",
  );
  assert.equal(talk.version, 9, "a readout has no version");
  talk = applyEvent(talk, event("session", { id: "ses_2" }));
  assert.equal(talk.reconnect, "ses_2");
  talk = applyEvent(talk, event("connected", {}));
  assert.equal(
    talk.reconnect,
    "ses_2",
    "nothing else changes it until the client reopens",
  );
});

test("a message sent shows at once, is replaced when its message arrives, and is given back when the send fails", () => {
  let talk = withSnapshot();
  talk = sent(talk, "p1", "Use a log scale.");
  const items = liveItems(talk);
  assert.deepEqual(items.at(-1), {
    kind: "owner",
    id: "p1",
    text: "Use a log scale.",
    pending: true,
  });
  assert.equal(items.filter((each) => each.kind === "owner").length, 2);
  talk = applyEvent(
    talk,
    event(
      "message",
      { type: "message", message: { id: "msg_3", role: "user", created: 300 } },
      8,
    ),
  );
  assert.equal(talk.pending.length, 1, "its text is not there yet");
  talk = applyEvent(
    talk,
    event(
      "part",
      {
        type: "part",
        message: "msg_3",
        part: { id: "prt_3", type: "text", text: "Use a log scale." },
      },
      9,
    ),
  );
  assert.deepEqual(
    talk.pending,
    [],
    "the owner's message arrived from the mirror",
  );
  assert.deepEqual(
    liveItems(talk)
      .filter((each) => each.kind === "owner")
      .map((each) => each.id),
    ["msg_1", "msg_3"],
  );
  talk = sent(talk, "p2", "And export it.");
  const [back, after] = failed(talk, "p2");
  assert.equal(back, "And export it.");
  assert.deepEqual(after.pending, []);
  const snapshot = applyEvent(
    sent(after, "p3", "Plot it."),
    event("snapshot", SNAPSHOT, 7),
  );
  assert.deepEqual(
    snapshot.pending,
    [],
    "a snapshot holding the text ends the pending message too",
  );
});
