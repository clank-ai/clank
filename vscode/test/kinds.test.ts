// Design 0002 §2.2 (decisions 0015, 0028): the TypeScript types generated from Clank's kinds describe what the API
// sends, so a question read from the API fits `Question`, field for field (the compiler checks it; the test reads it).

import assert from "node:assert/strict";
import { test } from "node:test";

import type { Question, RecordsByKind } from "../src/core/kinds";

test("a question as the API sends it fits the generated type", () => {
  const sent = {
    id: "q-1a2b3c",
    type: "approval",
    title: "Stop Docker Desktop?",
    detail: "2 containers that Clank did not start are running.",
    options: [
      { id: "stop", label: "Stop them and Docker", effect: "", key: "y", asks: null },
      { id: "cancel", label: "Cancel", effect: "", key: "n", asks: null },
    ],
    default: "cancel",
    expires: null,
    urgency: "normal",
    about: null,
    status: "waiting",
    asked: "2026-10-11T11:40:00.000Z",
    asked_by: { kind: "clank", via: "docker.stop" },
    operation_id: "op-1a2b3c4d",
    answer: null,
    reason: "",
  } satisfies Question;
  const question: RecordsByKind["question"] = sent;
  assert.equal(question.options[0]?.key, "y");
});
