// Design 0020 §10: "Annotate this PDF" asks the service for a PDF's pages (from the window's folder), then opens the
// one page there is, or the one picked from the list ("Page 3 of 12"), in the figure annotator; a refusal is said in the
// service's words, and a pick dismissed opens nothing.

import assert from "node:assert/strict";
import { test } from "node:test";

import { ClankError } from "../src/core/client";
import type { Api } from "../src/core/controller";
import { pageToMark } from "../src/core/pdf";
import type { Choice } from "../src/core/presenter";

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

const PAGES = (count: number) => ({
  pdf: "paper/main.pdf",
  built: true,
  pages: Array.from({ length: count }, (_, index) => ({
    number: index + 1,
    image: `.clank/latex/pages/paper-main/page-${index + 1}.png`,
  })),
});

test("a pdf of one page opens it at once; of several, the page picked", async () => {
  const asked: Array<{ path: string; body: unknown }> = [];
  const one = await pageToMark(api(PAGES(1), asked), "C:/work", "paper/main.pdf", async () => undefined);
  assert.deepEqual(one, { image: ".clank/latex/pages/paper-main/page-1.png" });
  assert.deepEqual(asked, [{ path: "agents/latex/pages", body: { folder: "C:/work", pdf: "paper/main.pdf" } }]);
  let offered: Array<Choice<string>> = [];
  const pick = async (items: Array<Choice<string>>) => {
    offered = items;
    return items[2]?.value;
  };
  const third = await pageToMark(api(PAGES(12), []), "C:/work", "paper/main.pdf", pick);
  assert.deepEqual(third, { image: ".clank/latex/pages/paper-main/page-3.png" });
  assert.equal(offered[2]?.label, "Page 3 of 12");
  assert.equal(offered[0]?.detail, "paper/main.pdf, as Clank built it (its lines found by SyncTeX)");
  assert.equal(await pageToMark(api(PAGES(3), []), "C:/work", "paper/main.pdf", async () => undefined), undefined);
});

test("a refusal is said in the service's words", async () => {
  const refused = new ClankError("x.pdf is not a file of the folder", 409, "refused");
  const said = await pageToMark(api(refused, []), "C:/work", "x.pdf", async () => undefined);
  assert.deepEqual(said, { error: "x.pdf is not a file of the folder" });
});
