// Design 0004 §5 (revised 2026-10-26): whether OpenCode reaches the model from the window's folder, as the service's
// `GET /agents/reach` says it, put in words: nothing when the way is fine; the problem with its fix's button in the
// status bar, a notification and the agent panel; OpenCode not started while it would fail at once (`blocked`). The fix
// is the route the service names, posted with a request key when the owner presses it. A service from before the route,
// or one too slow to say, gives nothing: the agent starts as before.

import assert from "node:assert/strict";
import { test } from "node:test";

import { applyFix, type Reach, reachNotice, reachStatus, readReach } from "../src/core/reach";

const BROKEN: Reach = {
  workspace: "paper",
  ready: false,
  blocked: true,
  problem:
    "paper's container cannot find the gateway's host `edge` ([Errno -3] Temporary failure in name resolution): its " +
    "network lost the edge, so OpenCode cannot reach the model",
  fix: { label: "Open the workspace again", post: "workspaces/open", body: { folder: "C:\\work\\paper" } },
  checks: [
    { name: "workspace", ok: true, said: "paper's container runs" },
    { name: "gateway", ok: true, said: "the gateway runs on port 18210" },
    { name: "edge", ok: false, said: "paper's container cannot find the gateway's host `edge`" },
    { name: "model", ok: true, said: "daily 262K is ready in the main slot" },
  ],
  seconds: 0.4,
};
const READY: Reach = { ...BROKEN, ready: true, blocked: false, problem: "", fix: null };
const NO_MODEL: Reach = {
  ...BROKEN, blocked: false, problem: "no model runs in the main slot (unloaded)",
  fix: { label: "Load daily 262K", post: "runtime/slots/main/load", body: { preset: "daily-262k" } },
};  // prettier-ignore
const LOADING: Reach = { ...BROKEN, blocked: false, problem: "the model is loading: daily 262K (its weights)", fix: null };

test("the way to the model is read for the folder, and a service that cannot say gives nothing", async () => {
  const asked: string[] = [];
  const api = {
    async get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T> {
      asked.push(`${path} ${JSON.stringify(parameters)}`);
      return BROKEN as T;
    },
    async post<T>(): Promise<T> {
      throw new Error("not posted");
    },
  };
  assert.deepEqual(await readReach(api, { folder: "C:\\work\\paper" }), BROKEN);
  assert.deepEqual(asked, ['agents/reach {"folder":"C:\\\\work\\\\paper"}']);
  const old = { ...api, get: async () => Promise.reject(new Error("the service answered 404")) };
  assert.equal(await readReach(old, { folder: "x" }), undefined, "a service from before the route");
  const slow = { ...api, get: async () => new Promise<never>(() => undefined) };
  assert.equal(await readReach(slow, { folder: "x" }, 20), undefined, "one too slow to say: nothing is held up");
});

test("the status bar says what stops OpenCode, or a fix it offers, and nothing when the way is fine", () => {
  assert.equal(reachStatus(undefined), undefined);
  assert.equal(reachStatus(READY), undefined);
  assert.deepEqual(reachStatus(BROKEN), {
    text: "$(error) OpenCode cannot reach the model",
    tooltip: `OpenCode cannot reach the model: ${BROKEN.problem}.\nClick: Open the workspace again.`,
  });
  assert.deepEqual(reachStatus(NO_MODEL), {
    text: "$(warning) No model runs",
    tooltip: "No model runs in the main slot (unloaded).\nClick: Load daily 262K.",
  });
  assert.equal(reachStatus(LOADING), undefined, "a model loading: the readout already says so");
});

test("the panel and the notification say the problem as a sentence, with the fix's button", () => {
  assert.deepEqual(reachNotice(BROKEN), {
    text: `OpenCode cannot reach the model: ${BROKEN.problem}.`,
    action: "Open the workspace again",
  });
  assert.deepEqual(reachNotice(NO_MODEL), { text: "No model runs in the main slot (unloaded).", action: "Load daily 262K" });
  assert.deepEqual(reachNotice(LOADING), { text: "The model is loading: daily 262K (its weights).", action: "" });
  assert.equal(reachNotice(READY), undefined);
});

test("a fix posts the route the service named, its body and a request key", async () => {
  const posted: unknown[] = [];
  const api = {
    async get<T>(): Promise<T> {
      throw new Error("not read");
    },
    async post<T>(path: string, body?: unknown, requestKey?: string): Promise<T> {
      posted.push([path, body, requestKey]);
      return { id: "op-1" } as T;
    },
  };
  await applyFix(api, BROKEN.fix!, "vscode-fix-1");
  assert.deepEqual(posted, [["workspaces/open", { folder: "C:\\work\\paper" }, "vscode-fix-1"]]);
});
