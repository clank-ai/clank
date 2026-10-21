// Design 0004 §5: in Clank's VS Code window the agent starts beside the files: for the folder the window has open,
// the folder's workspace is read; when its container runs, the agent's configuration is written into it and the
// terminal runs the command the service answers, named after the program and the workspace; otherwise it says what is
// missing and how to get it ready, and writes nothing. A window that has the agent's terminal (running, or only its tab,
// restored with a reloaded window before VS Code revives it) does not start another. With one OpenCode window per
// workspace (the service closed the others first), the new terminal replaces the window's agent terminals. The agent's
// group stays at the right edge: moved there when it is not, the keyboard given back to the group that had it.

import assert from "node:assert/strict";
import { test } from "node:test";

import { agentStart, agentTerminalOpen, rightward, type AgentApi } from "../src/core/agent";

const PREPARED = {
  workspace: "paper",
  program: "OpenCode",
  model: "daily 262K",
  argv: ["docker", "exec", "-it", "-w", "/workspace", "clank-h1-paper", "opencode"],
  one_window: true,
  closed: 1,
};

/** A service that answers the folder's view as given, and keeps what was asked. */
function service(
  view: { problem: string; workspace: string | null; state: string },
  prepared: Record<string, unknown> = PREPARED,
): AgentApi & { asked: string[] } {
  const asked: string[] = [];
  return {
    asked,
    async get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T> {
      asked.push(`GET ${path} ${JSON.stringify(parameters)}`);
      return view as T;
    },
    async post<T>(path: string, body?: unknown): Promise<T> {
      asked.push(`POST ${path} ${JSON.stringify(body)}`);
      return prepared as T;
    },
  };
}

test("a folder whose container runs gets the agent's terminal, with the command the service answers", async () => {
  const api = service({ problem: "", workspace: "paper", state: "running" });
  const found = await agentStart(api, "C:\\work\\paper");
  assert.deepEqual(found, {
    terminal: { name: "OpenCode · paper", program: "docker", args: PREPARED.argv.slice(1), replaces: true },
  });
  assert.deepEqual(api.asked, [
    'GET workspaces/folder {"folder":"C:\\\\work\\\\paper"}',
    'POST agents/prepare {"workspace":"paper"}',
  ]);
});

test("with one window per workspace the new terminal replaces the window's agent terminals, and otherwise adds one", async () => {
  const several = service({ problem: "", workspace: "paper", state: "running" }, { ...PREPARED, one_window: false });
  const found = await agentStart(several, "C:\\work\\paper");
  assert.ok("terminal" in found && found.terminal.replaces === false);
  const older = service({ problem: "", workspace: "paper", state: "running" }, { ...PREPARED, one_window: undefined });
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
