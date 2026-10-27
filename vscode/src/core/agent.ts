// Starting the agent beside the files (design 0004 §5): for the folder Clank's VS Code window has open, the folder's
// workspace as the service reads it; when its container runs, the agent's configuration is written into it and the
// command that starts the agent there is answered, for a terminal in the editor area; otherwise, what is missing and
// how to get it ready. The agent lives at the right edge of the editor area: its terminal opens in a group of its own
// there, a window that has it already (a reloaded one too) does not start another, and its group is moved back to the
// right edge when it is not there. With one OpenCode window per workspace (the workspace's record; the service closed
// the others first), the new terminal replaces the window's agent terminals. Revised 2026-10-26 (the owner: "an enormous
// amount of lag with getting the OpenCode terminal opened to the right"): the terminal's place shows at once, saying
// each step as it starts (`startingLines`); each call has a time limit, so a slow service is said, never waited on
// without end; and the agent's way to the model (`reach.ts`) is checked beside the configuration: while OpenCode would
// fail at once (its terminal closing with it), it is not started and the problem is said with its fix. A check slower
// than the configuration holds nothing up: the terminal starts and its answer comes after (`later`). Tested without
// VS Code.

import { inTime } from "./client";
import { type Reach, type ReachFix, readReach } from "./reach";

/** What starting the agent asks of the service. */
export interface AgentApi {
  get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T>;
  post<T>(path: string, body?: unknown, requestKey?: string): Promise<T>;
}

/** How long each step may take: the folder's workspace (two reads of Docker), and OpenCode's configuration (a few
 * Docker commands, and up to 10 s while another OpenCode window ends first). */
export const LIMITS = { folder: 15_000, prepare: 60_000 };
/** Once the configuration is written, how much longer the way to the model is waited for before OpenCode starts. */
export const REACH_GRACE_MS = 2_000;

/** A terminal that runs the agent: its name, its program and the program's arguments, and whether it replaces the
 * window's agent terminals (one window per workspace) or is added beside them. */
export interface AgentTerminal {
  name: string;
  program: string;
  args: string[];
  replaces: boolean;
}

/** The agent's terminal (with a problem on the way to the model that does not stop it, or the check still to come); or
 * why the agent cannot start yet, and what fixes it. */
export type AgentStart =
  | { terminal: AgentTerminal; workspace: string; reach?: Reach; later?: Promise<Reach | undefined> }
  | { problem: string; fix?: ReachFix; workspace?: string; reach?: Reach };

interface FolderView {
  problem: string;
  workspace: string | null;
  state: string;
}

interface Prepared {
  workspace: string;
  program: string;
  argv: string[];
  one_window?: boolean; // absent from a service from before one window per workspace
}

/** The agent's terminal for a folder, its configuration written into the folder's container and its way to the model
 * checked beside it; or what is missing. `say` hears each step as it starts; a step slower than its limit ends the
 * start with `TimedOut`. */
export async function agentStart(
  api: AgentApi,
  folder: string,
  say: (line: string) => void = () => undefined,
  graceMs: number = REACH_GRACE_MS,
  limits: { folder: number; prepare: number } = LIMITS,
): Promise<AgentStart> {
  say("reading the folder's workspace");
  const view = await inTime(api.get<FolderView>("workspaces/folder", { folder }), limits.folder, "the folder's workspace");
  if (view.problem) {
    return { problem: `this folder cannot be a workspace: ${view.problem}` };
  }
  if (!view.workspace || view.state !== "running") {
    return { problem: "its workspace's container does not run: `clank code` in a terminal here gets everything ready" };
  }
  const workspace = view.workspace;
  say(`writing OpenCode's configuration into ${workspace}'s container, and checking its way to the model`);
  const reaching = readReach(api, { workspace });
  const prepared = await inTime(
    api.post<Prepared>("agents/prepare", { workspace }),
    limits.prepare,
    "OpenCode's configuration",
  );
  let timer: ReturnType<typeof setTimeout> | undefined;
  const grace = new Promise<"later">((done) => {
    timer = setTimeout(() => done("later"), graceMs);
  });
  const waited = await Promise.race([reaching, grace]).finally(() => clearTimeout(timer));
  if (waited !== "later" && waited?.blocked) {
    const problem = `OpenCode cannot reach the model: ${waited.problem}`;
    return waited.fix ? { problem, fix: waited.fix, workspace, reach: waited } : { problem, workspace, reach: waited };
  }
  const [program, ...args] = prepared.argv;
  const replaces = prepared.one_window === true;
  const terminal = { name: `${prepared.program} · ${workspace}`, program, args, replaces };
  if (waited === "later") {
    return { terminal, workspace, later: reaching };
  }
  return waited && !waited.ready ? { terminal, workspace, reach: waited } : { terminal, workspace };
}

/** What the agent's terminal shows while OpenCode starts: where, each step said, and at its end a problem with its fix
 * and what Enter does there. */
export function startingLines(
  where: string,
  steps: string[],
  end?: { problem: string; fix?: string; enter: string },
): string[] {
  const lines = [`Clank · starting OpenCode in ${where}`, "", ...steps.map((step) => `  · ${step}`)];
  return end ? [...lines, ...problemLines(end.problem, end.fix, end.enter)] : lines;
}

/** A problem, the fix the service named (its button's words), and what Enter does. */
function problemLines(problem: string, fix: string | undefined, enter: string): string[] {
  const shown = [`  ✗ ${problem}`];
  if (fix) {
    shown.push(`    Its fix: ${fix} (the button in the notification, or in the agent panel).`);
  }
  return [...shown, `    Enter: ${enter}.`];
}

/** OpenCode's own log in a workspace's container, where it says why it ended. */
export const OPENCODE_LOG = "~/.local/share/opencode/log/opencode.log";

/** What the agent's place shows once OpenCode ended on its own with an error (its terminal closes with it): the exit
 * code, and the problem on its way to the model with its fix, or that the way works and where OpenCode said why. */
export function endedLines(where: string, code: number, problem?: { text: string; fix?: string }): string[] {
  const lines = [`Clank · OpenCode ended in ${where} (exit code ${code})`, ""];
  if (problem) {
    return [...lines, ...problemLines(problem.text, problem.fix, "start it again")];
  }
  return [
    ...lines,
    `  · its way to the model works: what it said last is in its log, in the workspace's container (${OPENCODE_LOG})`,
    "    Enter: start it again.",
  ];
}

/** The agent's terminals are named after the program and the workspace ("OpenCode · paper"). */
const AGENT_NAME = "OpenCode · ";
const PROCESS = 2; // VS Code's TerminalExitReason.Process: the terminal's program exited by itself

/** Whether a terminal that closed was the agent's, its program ended by itself with an error: not one the owner, the
 * window or Clank closed, nor OpenCode quit as asked (status 0). */
export function endedBadly(name: string, exit: { code: number | undefined; reason: number } | undefined): boolean {
  return name.startsWith(AGENT_NAME) && exit?.reason === PROCESS && exit.code !== undefined && exit.code !== 0;
}

/** Whether a window has the agent's terminal: one of its terminals, or a terminal tab restored with a reloaded window
 * (VS Code revives such a terminal after the extension starts, so only its tab is there at first). */
export function agentTerminalOpen(terminals: string[], terminalTabs: string[]): boolean {
  return [...terminals, ...terminalTabs].some((name) => name.startsWith(AGENT_NAME));
}

/** Keeping the agent's editor group at the right edge, for groups numbered 1 to `count` from the left: how many steps
 * to move it right, then the group to give the keyboard back to (the one that had it, where it is after the moves),
 * none when the agent's group had it. */
export function rightward(count: number, agent: number, active: number): { moves: number; refocus: number | undefined } {
  const moves = Math.max(count - agent, 0);
  if (moves === 0 || active === agent) {
    return { moves, refocus: undefined };
  }
  return { moves, refocus: active > agent ? active - 1 : active };
}
