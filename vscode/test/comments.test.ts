// Design 0020 §11: comments on lines of LaTeX files are sent to the agent together, each with its file (from the
// folder), its lines (counted from 1), the text it covers and its words, a thread's replies joined; threads already
// sent and empty ones are left out; once sent, each thread is labeled with the number the agent knows it by, and a
// refusal is said in the service's words.

import assert from "node:assert/strict";
import { test } from "node:test";

import { ClankError } from "../src/core/client";
import { type CommentThreadView, sendComments } from "../src/core/comments";
import type { Api } from "../src/core/controller";

function api(answer: unknown, asked: Array<{ path: string; body: unknown }>): Api {
  return {
    get: async () => {
      throw new Error("not read");
    },
    post: async <T>(path: string, body?: unknown): Promise<T> => {
      asked.push({ path, body });
      if (answer instanceof Error) {
        throw answer;
      }
      return answer as T;
    },
    events: async function* () {},
  };
}

const THREADS: CommentThreadView[] = [
  { file: "paper/intro.tex", start: 11, end: 12, text: "the rank grows\nexponentially", bodies: ["Say why.", "With a ref."], sent: false },
  { file: "paper/results.tex", start: 3, end: 3, text: "E_0 = -1.27", bodies: [], sent: false },
  { file: "paper/results.tex", start: 7, end: 7, text: "old", bodies: ["Done before."], sent: true },
  { file: "paper/results.tex", start: 3, end: 3, text: "E_0 = -1.27", bodies: ["Give the error bar."], sent: false },
];

test("the threads not sent yet go together, lines from 1, replies joined, and each gets its number", async () => {
  const asked: Array<{ path: string; body: unknown }> = [];
  const result = await sendComments(api({ count: 2, session: "ses_1" }, asked), "C:/work", THREADS);
  assert.deepEqual(asked, [{
    path: "agents/latex/comments",
    body: {
      folder: "C:/work",
      message: "",
      comments: [
        { file: "paper/intro.tex", start: 12, end: 13, text: "the rank grows\nexponentially", body: "Say why.\nWith a ref." },
        { file: "paper/results.tex", start: 4, end: 4, text: "E_0 = -1.27", body: "Give the error bar." },
      ],
    },
  }]);
  assert.deepEqual(result, { numbered: new Map([[0, 1], [3, 2]]), text: "2 comments sent to the agent" });
});

test("nothing to send, and a refusal, are said", async () => {
  const none = await sendComments(api({}, []), "C:/work", [THREADS[2]!]);
  assert.deepEqual(none, { error: "No comment to send: comment on a line of a .tex file first." });
  const refused = new ClankError("no agent runs in paper: start it", 409, "refused");
  assert.deepEqual(await sendComments(api(refused, []), "C:/work", THREADS), { error: "no agent runs in paper: start it" });
});
