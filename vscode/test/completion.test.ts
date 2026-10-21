// Design 0006 §5: completion asks the gateway only while it is on and its slot serves, after the wait, not when it was
// canceled meanwhile nor when the rest of the line holds more than closing brackets; it sends the lines before the
// current one (up to 120), the current line to the cursor and the lines after (up to 20); one line, or a few on an empty
// line after one that opens a block; the suggestion is one line when one was asked. The status bar item says whether it
// is on and served, and a click turns it off or on.

import assert from "node:assert/strict";
import { test } from "node:test";

import { Completer, type CompletionPresenter, type CompletionView, infill, suggestion, wanted } from "../src/core/completion";
import type { Api } from "../src/core/controller";
import type { ServerEvent } from "../src/core/events";

function view(enabled = true, status = "ready", lines: "one" | "few" = "few"): CompletionView {
  return {
    settings: { enabled, delay_ms: 120, lines },
    slot: { status, reason: "a test" },
    url: "http://127.0.0.1:18210/v1",
    problem: "",
  };
}

class FakePresenter implements CompletionPresenter {
  text = "";
  tooltip = "";
  shown = false;
  told: string[] = [];

  completion(text: string, tooltip: string, shown: boolean): void {
    [this.text, this.tooltip, this.shown] = [text, tooltip, shown];
  }

  info(text: string): void {
    this.told.push(text);
  }

  warn(text: string): void {
    this.told.push(`! ${text}`);
  }
}

/** The API: completion's view, and what was posted. */
function api(found: CompletionView): Api & { posts: unknown[] } {
  const posts: unknown[] = [];
  return {
    posts,
    get: async <T>() => found as T,
    post: async <T>(_path: string, body?: unknown) => {
      posts.push(body);
      Object.assign(found.settings, body as object);
      return found as T;
    },
    events: async function* (): AsyncGenerator<ServerEvent> {},
  };
}

/** A gateway that answers each request with `content`, keeping what was sent. */
function gateway(content: string): { fetcher: typeof fetch; sent: Array<{ url: string; body: unknown }> } {
  const sent: Array<{ url: string; body: unknown }> = [];
  const fetcher = (async (url: string, init?: { body?: string }) => {
    sent.push({ url, body: JSON.parse(init?.body ?? "null") });
    return new Response(JSON.stringify({ content, stop: true }), { status: 200 });
  }) as unknown as typeof fetch;
  return { fetcher, sent };
}

test("a request carries the lines before, the line to the cursor and the lines after; few lines after a block opens", () => {
  const before = Array.from({ length: 200 }, (_, n) => `line ${n}`).join("\n") + "\n    total = ";
  const body = infill(before, "\nnext\n" + "after\n".repeat(50), "few");
  assert.equal(body.prompt, "    total = ");
  assert.equal(body.input_prefix.split("\n").length - 1, 120, "120 lines before the current one");
  assert.ok(body.input_prefix.endsWith("line 199\n"));
  assert.equal(body.input_suffix.split("\n").length, 21, "the rest of the line and 20 more");
  assert.deepEqual([body.model, body.n_predict, body.stop], ["completion", 32, ["\n"]]);
  const opened = infill("def simulate(steps):\n    ", "", "few");
  assert.deepEqual([opened.n_predict, opened.stop], [64, ["\n\n"]], "an empty line after one that opens a block");
  assert.deepEqual(infill("def simulate(steps):\n    ", "", "one").stop, ["\n"]);
});

test("it asks only when the rest of the line is closing brackets or quotes", () => {
  assert.equal(wanted(""), true);
  assert.equal(wanted(")]} "), true);
  assert.equal(wanted('");'), true);
  assert.equal(wanted("x + 1)"), false);
});

test("a suggestion is one line when one was asked, without trailing spaces", () => {
  const one = infill("x = ", "", "one");
  assert.equal(suggestion({ content: "compute(steps)  \nmore" }, one), "compute(steps)");
  const few = infill("if x:\n", "", "few");
  assert.equal(suggestion({ content: "    a = 1\n    b = 2\n" }, few), "    a = 1\n    b = 2");
  assert.equal(suggestion({ broken_off: "a newer completion came" }, one), "");
});

test("it asks the gateway after the wait while it is on and served, and not when canceled, off or not served", async () => {
  const { fetcher, sent } = gateway("step * step");
  const waits: number[] = [];
  const completer = new Completer(new FakePresenter(), fetcher, async (ms) => {
    waits.push(ms);
  });
  const read = () => ({ before: "def f(step):\n    return ", after: "\n" });
  await completer.load(api(view()));
  assert.equal(await completer.complete(read, () => false), "step * step");
  assert.deepEqual(waits, [120]);
  assert.equal(sent[0]?.url, "http://127.0.0.1:18210/v1/infill");
  assert.equal(await completer.complete(read, () => true), undefined, "canceled while it waited");
  assert.equal(await completer.complete(() => ({ before: "f(", after: "x)" }), () => false), undefined);
  await completer.load(api(view(false)));
  assert.equal(await completer.complete(read, () => false), undefined, "off");
  await completer.load(api(view(true, "stopped")));
  assert.equal(await completer.complete(read, () => false), undefined, "its slot does not serve");
  assert.equal(sent.length, 1);
});

test("the status bar says whether completion is on and served, and a click turns it off and on", async () => {
  const presenter = new FakePresenter();
  const completer = new Completer(presenter, gateway("").fetcher);
  const service = api(view(true, "stopped"));
  await completer.load(service);
  assert.equal(presenter.text, "$(warning) Completion");
  assert.match(presenter.tooltip, /F8 in the console loads it/);
  await completer.toggle(service);
  assert.deepEqual(service.posts, [{ enabled: false }]);
  assert.equal(presenter.text, "$(circle-slash) Completion");
  await completer.event(api(view(true, "ready")), { name: "runtime.slot", id: 9, data: {} });
  assert.equal(presenter.text, "$(check) Completion");
  completer.disconnected();
  assert.equal(presenter.shown, false);
});
