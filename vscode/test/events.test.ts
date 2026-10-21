// Design 0002 §2.3 (decision 0017): the event stream's text is read into whole messages, whether a message arrives
// split across pieces or several arrive in one piece; a comment (the keepalive) is skipped, and a kept event has its id.

import assert from "node:assert/strict";
import { test } from "node:test";

import { EventReader } from "../src/core/events";

const ASKED = 'id: 7\nevent: question.asked\ndata: {"id":7,"type":"question.asked","summary":"Clank asks"}\n\n';

test("a message split across pieces is read once it is whole", () => {
  const reader = new EventReader();
  assert.deepEqual(reader.push(ASKED.slice(0, 20)), []);
  const [message] = reader.push(ASKED.slice(20));
  assert.deepEqual(message, {
    name: "question.asked",
    id: 7,
    data: { id: 7, type: "question.asked", summary: "Clank asks" },
  });
});

test("several messages in one piece are each read, and comments are skipped", () => {
  const reader = new EventReader();
  const text = "event: connected\ndata: {}\n\n: keepalive\n\n" + ASKED + 'event: operation.log\ndata: {"text":"step"}\n\n';
  const messages = reader.push(text);
  assert.deepEqual(
    messages.map((message) => [message.name, message.id]),
    [
      ["connected", undefined],
      ["question.asked", 7],
      ["operation.log", undefined],
    ],
  );
});
