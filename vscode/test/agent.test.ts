// Design 0004 §5: in Clank's VS Code window the agent starts beside the files: for the folder the window has open,
// the folder's workspace is read; when its container runs, the agent's configuration is written into it and the
// terminal runs the command the service answers, named after the program and the workspace; otherwise it says what is
// missing and how to get it ready, and writes nothing. A window that has the agent's terminal (running, or only its tab,
// restored with a reloaded window before VS Code revives it) does not start another. With one OpenCode window per
// workspace (the service closed the others first), the new terminal replaces the window's agent terminals. The agent's
// group stays at the right edge: moved there when it is not, the keyboard given back to the group that had it.
//
// Revised 2026-10-26 (the owner: "an enormous amount of lag with getting the OpenCode terminal opened to the right,
// and once the terminal is open it seems like the model immediately crashed"): the terminal's place shows at once and
// says each step as it starts; each call has a time limit; the agent's way to the model is checked beside the
// configuration, and OpenCode is not started while it would fail at once: the problem is said with its fix instead. A
// slow check holds nothing up: the terminal starts and the check's answer comes after. OpenCode that ends by itself
// with an error (its terminal closing with it) is told apart, and its place says why, with the fix.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  agentStart,
  agentTerminalOpen,
  endedBadly,
  endedLines,
  OPENCODE_LOG,
  rightward,
  startingLines,
  type AgentApi,
} from "../src/core/agent";
import { TimedOut } from "../src/core/client";
import type { Reach } from "../src/core/reach";

const PREPARED = {
  workspace: "paper",
  program: "OpenCode",
  model: "daily 262K",
  argv: ["docker", "exec", "-it", "-w", "/workspace", "clank-h1-paper", "opencode"],
  one_window: true,
  closed: 1,
};
const READY: Reach = {
  workspace: "paper", ready: true, blocked: false, problem: "", fix: null, checks: [], seconds: 0.3,
};  // prettier-ignore
const BROKEN: Reach = {
  ...READY, ready: false, blocked: true,
  problem: "paper's container cannot find the gateway's host `edge` (EAI_AGAIN)",
  fix: { label: "Open the workspace again", post: "workspaces/open", body: { folder: "C:\\work\\paper" } },
};  // prettier-ignore

type Answer = unknown | (() => Promise<unknown>);

/** A service that answers each route as given (a function: when it likes), and keeps what was asked. */
function service(
  view: { problem: string; workspace: string | null; state: string },
  prepared: Answer = PREPARED,
  reach: Answer = READY,
): AgentApi & { asked: string[] } {
  const asked: string[] = [];
  const answer = (given: Answer): Promise<unknown> =>
    typeof given === "function" ? (given as () => Promise<unknown>)() : Promise.resolve(given);
  return {
    asked,
    async get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T> {
      asked.push(`GET ${path} ${JSON.stringify(parameters)}`);
      return (await answer(path === "agents/reach" ? reach : view)) as T;
    },
    async post<T>(path: string, body?: unknown): Promise<T> {
      asked.push(`POST ${path} ${JSON.stringify(body)}`);
      return (await answer(prepared)) as T;
    },
  };
}

const RUNNING = { problem: "", workspace: "paper", state: "running" };

test("a folder whose container runs gets the agent's terminal, with the command the service answers", async () => {
  const api = service(RUNNING);
  const said: string[] = [];
  const found = await agentStart(api, "C:\\work\\paper", (line) => said.push(line));
  assert.deepEqual(found, {
    terminal: { name: "OpenCode · paper", program: "docker", args: PREPARED.argv.slice(1), replaces: true },
    workspace: "paper",
  });
  assert.deepEqual(api.asked, [
    'GET workspaces/folder {"folder":"C:\\\\work\\\\paper"}',
    'GET agents/reach {"workspace":"paper"}',
    'POST agents/prepare {"workspace":"paper"}',
  ], "the way to the model is checked beside the configuration, not after it");  // prettier-ignore
  assert.deepEqual(said, [
    "reading the folder's workspace",
    "writing OpenCode's configuration into paper's container, and checking its way to the model",
  ]);
});

test("with one window per workspace the new terminal replaces the window's agent terminals, and otherwise adds one", async () => {
  const several = service(RUNNING, { ...PREPARED, one_window: false });
  const found = await agentStart(several, "C:\\work\\paper");
  assert.ok("terminal" in found && found.terminal.replaces === false);
  const older = service(RUNNING, { ...PREPARED, one_window: undefined });
  const before = await agentStart(older, "C:\\work\\paper");
  assert.ok("terminal" in before && before.terminal.replaces === false, "a service from before says nothing: adds");
});

test("a folder that is not ready says what is missing and how to get it ready, and writes nothing", async () => {
  const stopped = service({ problem: "", workspace: "paper", state: "exited" });
  assert.deepEqual(await agentStart(stopped, "C:\\work\\paper"), {
    problem: "its workspace's container does not run: `clank code` in a terminal here gets everything ready",
  });
  const refused = service({ problem: "it is a drive's root", workspace: null, state: "" });
  assert.deepEqual(await agentStart(refused, "D:\\"), {
    problem: "this folder cannot be a workspace: it is a drive's root",
  });
  assert.ok(![...stopped.asked, ...refused.asked].some((line) => line.startsWith("POST")));
});

test("OpenCode is not started while it cannot reach the model: the problem is said with its fix", async () => {
  const api = service(RUNNING, PREPARED, BROKEN);
  assert.deepEqual(await agentStart(api, "C:\\work\\paper"), {
    problem: "OpenCode cannot reach the model: paper's container cannot find the gateway's host `edge` (EAI_AGAIN)",
    fix: BROKEN.fix,
    workspace: "paper",
    reach: BROKEN,
  });
});

test("a problem that does not stop OpenCode comes with its terminal, and a service without the check starts it as before", async () => {
  const loading: Reach = { ...READY, ready: false, problem: "the model is loading: daily 262K (its weights)" };
  const found = await agentStart(service(RUNNING, PREPARED, loading), "C:\\work\\paper");
  assert.ok("terminal" in found);
  assert.deepEqual(found.reach, loading);
  const old = service(RUNNING, PREPARED, () => Promise.reject(new Error("the service answered 404")));
  const before = await agentStart(old, "C:\\work\\paper");
  assert.ok("terminal" in before && before.reach === undefined && before.later === undefined);
});

test("a slow check holds nothing up: the terminal starts, and the check's answer comes after", async () => {
  let answer: (reach: Reach) => void = () => undefined;
  const slow = new Promise<Reach>((resolve) => {
    answer = resolve;
  });
  const found = await agentStart(service(RUNNING, PREPARED, () => slow), "C:\\work\\paper", () => undefined, 20);
  assert.ok("terminal" in found && found.reach === undefined && found.later !== undefined);
  answer(BROKEN);
  assert.deepEqual(await found.later, BROKEN, "said once it comes, as for an agent that ended");
});

test("a service too slow to answer ends the start with its words, never a wait without end", async () => {
  const hung = service(RUNNING, () => new Promise<never>(() => undefined));
  await assert.rejects(agentStart(hung, "C:\\work\\paper", () => undefined, 20, { folder: 50, prepare: 30 }), (error: unknown) => {
    assert.ok(error instanceof TimedOut);
    assert.equal(error.message, "the Clank service did not answer OpenCode's configuration within 0.03 s");
    return true;
  });  // prettier-ignore
});

test("the starting terminal says where OpenCode starts, each step, and a problem with its fix and what Enter does", () => {
  assert.deepEqual(startingLines("paper", ["reading the folder's workspace"]), [
    "Clank · starting OpenCode in paper",
    "",
    "  · reading the folder's workspace",
  ]);
  assert.deepEqual(
    startingLines("paper", [], { problem: BROKEN.problem, fix: "Open the workspace again", enter: "try again" }),
    [
      "Clank · starting OpenCode in paper",
      "",
      "  ✗ paper's container cannot find the gateway's host `edge` (EAI_AGAIN)",
      "    Its fix: Open the workspace again (the button in the notification, or in the agent panel).",
      "    Enter: try again.",
    ],
  );
});

test("OpenCode that ended by itself with an error is told apart from one quit, closed or ended with its window", () => {
  assert.equal(endedBadly("OpenCode · paper", { code: 1, reason: 2 }), true, "its program exited with 1");
  assert.equal(endedBadly("OpenCode · paper", { code: 0, reason: 2 }), false, "quit as asked");
  assert.equal(endedBadly("OpenCode · paper", { code: undefined, reason: 3 }), false, "the owner closed it");
  assert.equal(endedBadly("OpenCode · paper", { code: 1, reason: 1 }), false, "the window closed or reloaded");
  assert.equal(endedBadly("OpenCode · paper", { code: 1, reason: 4 }), false, "Clank replaced it");
  assert.equal(endedBadly("pwsh", { code: 1, reason: 2 }), false, "not the agent's");
  assert.equal(endedBadly("OpenCode · paper", undefined), false);
});

test("the agent's place says that OpenCode ended, with what stops it and its fix, or where it said why", () => {
  assert.deepEqual(endedLines("paper", 1, { text: "OpenCode cannot reach the model: the gateway does not run", fix: "Start the gateway" }), [
    "Clank · OpenCode ended in paper (exit code 1)",
    "",
    "  ✗ OpenCode cannot reach the model: the gateway does not run",
    "    Its fix: Start the gateway (the button in the notification, or in the agent panel).",
    "    Enter: start it again.",
  ]);  // prettier-ignore
  assert.deepEqual(endedLines("paper", 1), [
    "Clank · OpenCode ended in paper (exit code 1)",
    "",
    `  · its way to the model works: what it said last is in its log, in the workspace's container (${OPENCODE_LOG})`,
    "    Enter: start it again.",
  ]);
});

test("the agent's terminal counts as open when it runs, or when only its tab came back with a reloaded window", () => {
  assert.equal(agentTerminalOpen(["bash"], []), false);
  assert.equal(agentTerminalOpen(["OpenCode · paper"], []), true);
  assert.equal(agentTerminalOpen([], ["OpenCode · paper"]), true, "restored before VS Code revives the terminal");
  assert.equal(agentTerminalOpen(["pwsh"], ["Python REPL"]), false);
});

test("the agent's group is moved to the right edge, and the keyboard goes back to the group that had it", () => {
  assert.deepEqual(rightward(2, 2, 1), { moves: 0, refocus: undefined }, "already at the right edge");
  assert.deepEqual(rightward(2, 1, 1), { moves: 1, refocus: undefined }, "it had the keyboard: it keeps it");
  assert.deepEqual(rightward(2, 1, 2), { moves: 1, refocus: 1 }, "a file opened to its right moves left of it");
  assert.deepEqual(rightward(3, 1, 3), { moves: 2, refocus: 2 });
  assert.deepEqual(rightward(3, 2, 1), { moves: 1, refocus: 1 }, "a group left of it stays where it is");
});
