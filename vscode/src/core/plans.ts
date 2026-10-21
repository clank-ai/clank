// Plans in the editor (design 0009 §7, §8): a Markdown file whose header says `kind: plan` gets buttons that hand it to
// the coding agent: Implement with Review, Implement with Auto, and Continue when some of its checklist is done. What
// a plan is mirrors Clank's `clank/components/agents/plans.py`: the file's first line is `---`, the header ends at the
// next `---` line (spaces after either, and Windows line endings, are allowed), and only a line `kind: plan` inside
// it counts; no file in a folder agents load their settings from, and no AGENTS.md or CLAUDE.md, is a plan. The
// requests go to the service (`agents/implement`); VS Code is reached only through a presenter, so this is tested
// without it.

import { ClankError } from "./client";
import type { Api } from "./controller";

const KIND = /^kind:\s*plan\s*$/;
const SETTINGS = [".opencode", ".claude", ".git", ".github", ".vscode"];
const INSTRUCTIONS = ["agents.md", "claude.md"];
const NO_WINDOW = "no OpenCode runs in a window";
const WINDOW_LOOK_MS = 500; // how often the workspace's servers are looked at while the agent's window starts
const WINDOW_WAIT_MS = 30_000; // the longest the window is waited for (it took 3 s on a quiet machine, 2026-10-16)

/** The mode an implementation runs in. */
export type ImplementMode = "review" | "auto";

/** Whether a file, by its path in the folder (`/` between parts), may be a plan: Markdown, inside, not a settings file. */
export function planPath(relative: string): boolean {
  if (!relative || relative.startsWith("/") || !relative.toLowerCase().endsWith(".md")) {
    return false;
  }
  const parts: string[] = [];
  for (const part of relative.split("/")) {
    if (part === "..") {
      if (!parts.pop()) {
        return false;
      }
    } else if (part !== "." && part !== "") {
      parts.push(part);
    }
  }
  const last = (parts[parts.length - 1] ?? "").toLowerCase();
  return parts.length > 0 && !parts.some((part) => SETTINGS.includes(part)) && !INSTRUCTIONS.includes(last);
}

/** Whether a file's text is a plan's: a header that says `kind: plan`. */
export function isPlan(text: string | null | undefined): boolean {
  if (!text) {
    return false;
  }
  const lines = text.split(/\r\n|\n|\r/);
  if (lines[0]?.trimEnd() !== "---") {
    return false;
  }
  let found = false;
  for (const line of lines.slice(1)) {
    if (line.trimEnd() === "---") {
      return found;
    }
    found = found || KIND.test(line);
  }
  return false; // a header that never closes is not one
}

/** The checklist of a plan: how many items are done, and how many there are. */
export function stepCounts(text: string): { done: number; total: number } {
  let [done, total] = [0, 0];
  for (const line of text.split(/\r\n|\n|\r/)) {
    const item = /^\s*[-*+]\s+\[([ xX])\]/.exec(line);
    if (item) {
      total += 1;
      done += item[1] === " " ? 0 : 1;
    }
  }
  return { done, total };
}

/** A button on a plan: its title and the command it runs. */
export interface Lens {
  title: string;
  command: "clank.implementReview" | "clank.implementAuto" | "clank.implementContinue";
}

/** The buttons a file's text gets: none when it is not a plan; Continue only when some steps are done. */
export function lenses(text: string): Lens[] {
  if (!isPlan(text)) {
    return [];
  }
  const { done, total } = stepCounts(text);
  const buttons: Lens[] = [
    { title: "▶ Implement with Review", command: "clank.implementReview" },
    { title: "▶ Implement with Auto", command: "clank.implementAuto" },
  ];
  if (total > 0 && done > 0) {
    buttons.push({ title: `↻ Continue (${done} of ${total} steps done)`, command: "clank.implementContinue" });
  }
  return buttons;
}

/** The plan's path relative to the workspace's folder, with `/` between parts; undefined when it is outside. */
export function relativePlan(file: string, folder: string, caseless: boolean): string | undefined {
  const plain = (path: string): string => path.replace(/\\/g, "/").replace(/\/+$/, "");
  const [one, root] = [plain(file), plain(folder)];
  const [a, b] = caseless ? [one.toLowerCase(), root.toLowerCase()] : [one, root];
  return a.startsWith(b + "/") ? one.slice(root.length + 1) : undefined;
}

/** VS Code, as implementing a plan sees it. */
export interface ImplementPresenter {
  /** Save the plan's document when it has unsaved changes. */
  save(): Promise<void>;
  /** Show the agent's terminal if the window has it. */
  reveal(): void;
  /** Start the agent beside the files (`clank.openAgent`), resolving once it is started. */
  openAgent(): Promise<void>;
  /** Say something with one button: whether it was clicked. */
  offer(text: string, button: string): Promise<boolean>;
  info(text: string): void;
  warn(text: string): void;
  /** Wait a while (between looks for the agent's window). */
  wait(ms: number): Promise<void>;
}

/** The plan being implemented: the folder of its workspace, and its file. */
export interface PlanFile {
  folder: string;
  file: string;
  caseless: boolean;
}

interface FolderView {
  problem: string;
  workspace: string | null;
}

interface Servers {
  servers: Array<{ terminal?: boolean }>;
}

/** Wait until an OpenCode window runs in the workspace (a server that runs a terminal interface is seen), half a
 * minute at most; a look that fails (the container or its bridge not answering yet) is followed by another. */
async function windowStarted(api: Pick<Api, "get">, presenter: ImplementPresenter, workspace: string): Promise<void> {
  for (let waited = 0; waited < WINDOW_WAIT_MS; waited += WINDOW_LOOK_MS) {
    await presenter.wait(WINDOW_LOOK_MS);
    try {
      const { servers } = await api.get<Servers>("agents/sessions", { workspace });
      if (servers.some((server) => server.terminal)) {
        return;
      }
    } catch {
      // not answering yet: look again
    }
  }
}

/** Hand a plan to the agent in a mode; false when it was not handed over (the reason said). With no window, the agent
 * is offered; once opened, the plan is handed over again when its window runs. */
export async function implement(
  api: Pick<Api, "get" | "post">,
  presenter: ImplementPresenter,
  plan: PlanFile,
  mode: ImplementMode,
  retried = false,
): Promise<boolean> {
  let workspace = "";
  try {
    await presenter.save();
    const view = await api.get<FolderView>("workspaces/folder", { folder: plan.folder });
    if (view.problem || !view.workspace) {
      presenter.warn(view.problem ? `this folder cannot be a workspace: ${view.problem}` : "this folder has no Clank workspace");
      return false;
    }
    workspace = view.workspace;
    const relative = relativePlan(plan.file, plan.folder, plan.caseless);
    if (relative === undefined) {
      presenter.warn("the plan is not inside the window's folder");
      return false;
    }
    await api.post("agents/implement", { workspace, plan: relative, mode });
    presenter.info(`Implementing ${relative} with ${mode === "auto" ? "Auto" : "Review"}: the agent's window shows it`);
    presenter.reveal();
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (error instanceof ClankError && error.status === 409 && message.includes(NO_WINDOW) && !retried && workspace) {
      if (await presenter.offer(message, "Open the agent")) {
        await presenter.openAgent();
        await windowStarted(api, presenter, workspace);
        return implement(api, presenter, plan, mode, true);
      }
      return false;
    }
    presenter.warn(message);
    return false;
  }
}
