// Design 0002 §2.5 and §2.7: against a real Clank service (the Python suite starts one and names it in CLANK_TEST_URL
// and CLANK_TEST_TOKEN), the client lists the question waiting and answers it with CLANK_TEST_OPTION.

import assert from "node:assert/strict";
import { test } from "node:test";

import { ClankClient } from "../src/core/client";
import type { Question } from "../src/core/kinds";

const url = process.env["CLANK_TEST_URL"];
const token = process.env["CLANK_TEST_TOKEN"];

test("the client lists the waiting question and answers it", { skip: !url || !token }, async () => {
  const client = new ClankClient(url ?? "", token ?? "");
  const waiting = await client.get<Question[]>("questions");
  assert.equal(waiting.length, 1);
  const answered = await client.post<Question>(`questions/${waiting[0]!.id}/answer`, {
    option: process.env["CLANK_TEST_OPTION"],
  });
  assert.equal(answered.answer?.by.via, "vscode");
});
