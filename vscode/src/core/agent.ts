// Starting the agent beside the files (design 0004 §5): for the folder Clank's VS Code window has open, the folder's
// workspace as the service reads it; when its container runs, the agent's configuration is written into it and the
// command that starts the agent there is answered, for a terminal in the editor area; otherwise, what is missing and
// how to get it ready. The agent lives at the right edge of the editor area: its terminal opens in a group of its own
// there, a window that has it already (a reloaded one too) does not start another, and its group is moved back to the
// right edge when it is not there. With one OpenCode window per workspace (the workspace's record; the service closed
// the others first), the new terminal replaces the window's agent terminals. Tested without VS Code.

/** What starting the agent asks of the service. */
export interface AgentApi {
  get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T>;
  post<T>(path: string, body?: unknown, requestKey?: string): Promise<T>;
}

/** A terminal that runs the agent: its name, its program and the program's arguments, and whether it replaces the
 * window's agent terminals (one window per workspace) or is added beside them. */
export interface AgentTerminal {
  name: string;
  program: string;
  args: string[];
  replaces: boolean;
}

/** The agent's terminal, or why the agent cannot start yet. */
export type AgentStart = { terminal: AgentTerminal } | { problem: string };

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

/** The agent's terminal for a folder, its configuration written into the folder's container; or what is missing. */
export async function agentStart(api: AgentApi, folder: string): Promise<AgentStart> {
  const view = await api.get<FolderView>("workspaces/folder", { folder });
  if (view.problem) {
    return { problem: `this folder cannot be a workspace: ${view.problem}` };
  }
  if (!view.workspace || view.state !== "running") {
    return { problem: "its workspace's container does not run: `clank code` in a terminal here gets everything ready" };
  }
  const prepared = await api.post<Prepared>("agents/prepare", { workspace: view.workspace });
  const [program, ...args] = prepared.argv;
  const replaces = prepared.one_window === true;
  return { terminal: { name: `${prepared.program} · ${view.workspace}`, program, args, replaces } };
}

/** The agent's terminals are named after the program and the workspace ("OpenCode · paper"). */
const AGENT_NAME = "OpenCode · ";

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
