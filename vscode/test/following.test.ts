// Design 0023 §5: the agent panel's decisions about the stream it follows (pure, so Node tests them without VS Code).
// A stream is resumed from its version only on the same session; a broken stream is opened again after a wait that
// doubles up to eight seconds, and after three failures in a row the panel polls instead; the header says which; the
// older pages the owner read stay through a snapshot of the same session and go with another session's.

import assert from "node:assert/strict";
import { test } from "node:test";

import type { Conversation } from "../src/core/conversation";
import { headerLink, nextWait, pagesAfterSnapshot, pollsAfter, streamParameters } from "../src/core/following";
import { applyEvent, emptyTalk } from "../src/core/talking";

const SNAPSHOT: Conversation & { version: number } = {
  folder: "C:/work/paper", workspace: "paper",
  session: { id: "ses_1", title: "A plan", port: 4096, busy: false },
  messages: [{ info: { id: "msg_1", role: "user", created: 100 }, parts: [] }],
  next: "msg_0", waiting: { permissions: [], questions: [] }, version: 7,
}; // prettier-ignore

test("the stream is resumed from its version on the same session, and opened fresh otherwise", () => {
  const fresh = streamParameters(emptyTalk(), "C:/work/paper", "", 30);
  assert.deepEqual(fresh, { folder: "C:/work/paper", session: "", limit: 30 });
  const talk = applyEvent(emptyTalk(), { name: "snapshot", id: 7, data: SNAPSHOT });
  assert.deepEqual(streamParameters(talk, "C:/work/paper", "", 30), {
    folder: "C:/work/paper", session: "", limit: 30, after: 7, after_session: "ses_1",
  }); // prettier-ignore
  assert.deepEqual(
    streamParameters(talk, "C:/work/paper", "ses_2", 30),
    { folder: "C:/work/paper", session: "ses_2", limit: 30 },
    "another session pinned: nothing of the old one's is resumed",
  );
});

test("a broken stream is opened again after a wait that doubles up to eight seconds, then the panel polls", () => {
  assert.equal(nextWait(1000), 2000);
  assert.equal(nextWait(4000), 8000);
  assert.equal(nextWait(8000), 8000);
  assert.equal(pollsAfter(2), false);
  assert.equal(pollsAfter(3), true);
  assert.equal(headerLink(false, 0), "");
  assert.equal(headerLink(false, 1), "reconnecting…");
  assert.equal(headerLink(true, 3), "polling");
});

test("the older pages stay through a snapshot of the same session and go with another session's", () => {
  const older = [{ info: { id: "msg_0", role: "user" as const, created: 50 }, parts: [] }];
  const same = pagesAfterSnapshot("ses_1", { ...SNAPSHOT, next: "msg_00" }, older, "msg_-1");
  assert.deepEqual(same, { older, cursor: "msg_-1" }, "the cursor is the older pages' while there are some");
  const none = pagesAfterSnapshot("ses_1", { ...SNAPSHOT, next: "msg_00" }, [], "stale");
  assert.deepEqual(none, { older: [], cursor: "msg_00" }, "no older page read: the cursor is the snapshot's");
  const other = pagesAfterSnapshot("ses_0", SNAPSHOT, older, "msg_-1");
  assert.deepEqual(other, { older: [], cursor: "msg_0" });
  const first = pagesAfterSnapshot(undefined, SNAPSHOT, [], "");
  assert.deepEqual(first, { older: [], cursor: "msg_0" });
});
