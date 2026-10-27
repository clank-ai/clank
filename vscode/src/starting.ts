// The agent's place at the right edge while OpenCode starts, and after it ended (design 0004 §5, revised 2026-10-26).
// The owner found "an enormous amount of lag with getting the OpenCode terminal opened to the right": no terminal showed
// until the service had prepared the agent. Now a terminal of Clank's own (a pseudoterminal) takes the agent's place at
// once, says each step as it starts, and OpenCode's terminal replaces it in its place once the service answers its
// command; the readout and the agent panel open beside it meanwhile. When something stops OpenCode (the service does
// not answer, the folder is not ready, OpenCode could not reach the model), the place says what and how to fix it,
// Enter tries again (or starts the service), and a notification offers the fix the service named, which is posted when
// pressed, OpenCode then started once its way to the model works. OpenCode that ends by itself with an error closes its
// terminal: the place comes back saying why, with the fix. A problem on the way to the model is looked at again every
// little while until it is gone, for the status bar and the agent panel. The logic is `core/agent.ts` and
// `core/reach.ts`; this is the glue to VS Code's terminals.

import { spawn } from "node:child_process";
import { basename } from "node:path";

import * as vscode from "vscode";

import { agentStart, type AgentStart, endedBadly, endedLines, startingLines } from "./core/agent";
import { type ClankClient, NotRunning } from "./core/client";
import { applyFix, type Reach, type ReachFix, reachNotice, readReach } from "./core/reach";
import { closeEmptyGroups } from "./readout";

const AGENT_TERMINAL = "OpenCode · "; // the names of the agent's terminals, and of its place, start with this
const WAIT_MS = 2_000; // the service is looked for this often while it does not answer
const SERVICE_WAIT_MS = 120_000; // for this long, before the place says so and waits for Enter
const WATCH_MS = 15_000; // a problem on the way to the model is looked at again this often, until it is gone
const FIXED_MS = 3_000; // after a fix was pressed, the way is looked at this often
const FIXED_TRIES = 60; // for three minutes

/** What the agent's place needs of the rest of the extension. */
export interface StarterHost {
  connect(): ClankClient | undefined;
  home(): string;
  info(text: string): void;
  warn(text: string): void;
  /** The agent's place shows at the right edge: the readout and the agent panel open with it. */
  placed(): void;
  /** What stands in the agent's way to the model now (undefined: nothing, or not known). */
  reached(reach: Reach | undefined): void;
  newKey(): string;
}

function words(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** The column of the editor group holding a terminal tab whose name starts with `name`. */
function columnOf(name: string): vscode.ViewColumn | undefined {
  return vscode.window.tabGroups.all.find((group) =>
    group.tabs.some((tab) => tab.input instanceof vscode.TabInputTerminal && tab.label.startsWith(name)),
  )?.viewColumn;
}

/** A new group at the right edge of the editor area. */
function rightEdge(): vscode.ViewColumn {
  return (vscode.window.tabGroups.all.length + 1) as vscode.ViewColumn;
}

/** A terminal of Clank's own in the agent's place: its lines drawn whole, Enter given to `enter`. */
class Place implements vscode.Pseudoterminal {
  private readonly writer = new vscode.EventEmitter<string>();
  private readonly namer = new vscode.EventEmitter<string>();
  readonly onDidWrite = this.writer.event;
  readonly onDidChangeName = this.namer.event;
  readonly terminal: vscode.Terminal;
  name: string;
  closed = false;
  enter: (() => void) | undefined;
  private lines: string[] = [];
  private opened = false;

  constructor(where: string, column: vscode.ViewColumn) {
    this.name = `${AGENT_TERMINAL}${where}`;
    this.terminal = vscode.window.createTerminal({
      name: this.name,
      pty: this,
      iconPath: new vscode.ThemeIcon("loading~spin"),
      location: { viewColumn: column },
      isTransient: true,
    });
  }

  open(): void {
    this.opened = true;
    this.paint();
  }

  close(): void {
    this.closed = true;
  }

  handleInput(data: string): void {
    if (data === "\r") {
      this.enter?.();
    }
  }

  draw(lines: string[]): void {
    this.lines = lines;
    if (this.opened) {
      this.paint();
    }
  }

  rename(where: string): void {
    this.name = `${AGENT_TERMINAL}${where}`;
    this.namer.fire(this.name);
  }

  private paint(): void {
    this.writer.fire(`\x1b[2J\x1b[3J\x1b[H${this.lines.join("\r\n")}\r\n`);
  }
}

/** Starting OpenCode beside the files, its place shown first; and what stands in its way, said with its fix. */
export class AgentStarter implements vscode.Disposable {
  private place: Place | undefined;
  private busy = false;
  private watching: ReturnType<typeof setTimeout> | undefined;
  private shown: Reach | undefined; // the problem on the way to the model shown now

  constructor(private readonly host: StarterHost) {}

  dispose(): void {
    clearTimeout(this.watching);
    this.place?.terminal.dispose();
  }

  /** Start OpenCode beside the files of the window's folder: its place shown at once, each step said, OpenCode's
   * terminal in its place once the service answers; what stops it said there, with its fix. */
  async start(): Promise<void> {
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!folder) {
      this.host.warn("open a folder first: the agent works in the folder the window has open");
      return;
    }
    if (this.busy) {
      this.place?.terminal.show();
      return;
    }
    this.busy = true;
    try {
      await this.run(folder);
    } finally {
      this.busy = false;
    }
  }

  /** The fix of the problem shown now, pressed in the status bar or the agent panel; with none, a look again. */
  async fixShown(): Promise<void> {
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!folder) {
      return;
    }
    if (this.shown?.fix) {
      await this.fix(this.shown.fix, folder);
      return;
    }
    const client = this.host.connect();
    const reach = client ? await readReach(client, { folder }) : undefined;
    this.report(reach, folder);
    this.host.info(reach === undefined ? "the Clank service cannot say now" : (reachNotice(reach)?.text ?? "OpenCode's way to the model works."));
  }

  /** A terminal closed: when it was OpenCode ending by itself with an error, its place comes back saying why. */
  async ended(terminal: vscode.Terminal): Promise<void> {
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const exit = terminal.exitStatus;
    if (!folder || this.busy || !endedBadly(terminal.name, exit) || exit?.code === undefined) {
      return;
    }
    const where = terminal.name.slice(AGENT_TERMINAL.length);
    const place = await this.placeFor(where);
    place.draw([`Clank · OpenCode ended in ${where} (exit code ${exit.code})`, "", "  · looking at its way to the model"]);
    place.enter = () => void this.start();
    const client = this.host.connect();
    const reach = client ? await readReach(client, { folder }) : undefined;
    const notice = reachNotice(reach);
    place.draw(endedLines(where, exit.code, notice ? { text: notice.text, fix: notice.action || undefined } : undefined));
    this.report(reach, folder);
    const again = "Start OpenCode again";
    const fix = reach?.fix;
    const said = `Clank: OpenCode ended (exit code ${exit.code})${notice ? `: ${notice.text}` : "; its way to the model works."}`;
    const chosen = await vscode.window.showWarningMessage(said, ...(fix ? [fix.label] : []), again);
    if (chosen === again) {
      void this.start();
    } else if (fix && chosen === fix.label) {
      void this.fix(fix, folder);
    }
  }

  private async run(folder: string): Promise<void> {
    let where = basename(folder) || folder;
    const place = await this.placeFor(where);
    const steps: string[] = [];
    const say = (line: string): void => {
      steps.push(line);
      place.draw(startingLines(where, steps));
    };
    place.enter = undefined;
    place.draw(startingLines(where, steps));
    let found: AgentStart | undefined;
    for (let waited = 0; found === undefined; waited += WAIT_MS) {
      if (place.closed) {
        return; // the owner closed the place: nothing more is started
      }
      const client = this.host.connect();
      if (client) {
        try {
          found = await agentStart(client, folder, say);
        } catch (error) {
          if (!(error instanceof NotRunning)) {
            found = { problem: words(error) }; // a refusal in the service's words, or too slow an answer
          }
        }
      }
      if (found !== undefined) {
        break;
      }
      if (waited === 0) {
        say(`the Clank service does not answer (${this.host.home()}); looked for every few seconds. Enter starts it`);
        place.enter = () => this.startService(say);
      }
      if (waited >= SERVICE_WAIT_MS) {
        place.draw(startingLines(where, steps, { problem: "the Clank service does not answer", enter: "start it, then OpenCode" }));
        place.enter = () => {
          this.startService(say);
          void this.start();
        };
        return;
      }
      await delay(WAIT_MS);
    }
    if (found.workspace && found.workspace !== where) {
      where = found.workspace;
      place.rename(where);
    }
    if ("terminal" in found) {
      this.open(place, found, folder);
      return;
    }
    place.draw(startingLines(where, steps, { problem: found.problem, fix: found.fix?.label, enter: "try again" }));
    place.enter = () => void this.start();
    this.report(found.reach, folder);
    const fix = found.fix;
    if (fix) {
      void vscode.window.showWarningMessage(`Clank: ${found.problem}.`, fix.label).then((chosen) => {
        if (chosen === fix.label) {
          void this.fix(fix, folder);
        }
      });
    } else {
      this.host.warn(`OpenCode is not started: ${found.problem}`);
    }
  }

  /** The agent's place: the one shown, else a new one at the right edge, the readout and the panel opened with it. */
  private async placeFor(where: string): Promise<Place> {
    if (this.place && !this.place.closed) {
      this.place.terminal.show();
      return this.place;
    }
    await closeEmptyGroups(); // a reloaded window's empty places, so the agent's place goes beside the files
    const place = new Place(where, columnOf(AGENT_TERMINAL) ?? rightEdge());
    this.place = place;
    place.terminal.show();
    this.host.placed();
    return place;
  }

  /** OpenCode's terminal in its place, the place closed; the problem on its way that does not stop it said. */
  private open(place: Place, found: Extract<AgentStart, { terminal: unknown }>, folder: string): void {
    const column = columnOf(place.name) ?? rightEdge();
    const focus = vscode.window.activeTerminal === place.terminal;
    if (found.terminal.replaces) {
      // one OpenCode window per workspace: the service closed the others, so their tabs go too
      vscode.window.terminals
        .filter((each) => each !== place.terminal && each.name.startsWith(AGENT_TERMINAL))
        .forEach((each) => each.dispose());
    }
    const terminal = vscode.window.createTerminal({
      name: found.terminal.name,
      shellPath: found.terminal.program,
      shellArgs: found.terminal.args,
      location: { viewColumn: column, preserveFocus: !focus },
      // Never revived by VS Code: a revived terminal ran its saved command again, with a port another OpenCode had by
      // then, out of Clank's reach (2026-10-16). A reloaded window starts the agent afresh instead.
      isTransient: true,
    });
    terminal.show(!focus);
    place.terminal.dispose();
    if (this.place === place) {
      this.place = undefined;
    }
    this.report(found.reach, folder);
    void found.later?.then((reach) => {
      this.report(reach, folder);
      const notice = reachNotice(reach);
      if (reach?.blocked && notice) {
        this.host.warn(notice.text);
      }
    });
  }

  /** Show what stands in the way to the model (or nothing), and look again every little while until it is gone. */
  private report(reach: Reach | undefined, folder: string): void {
    this.shown = reach && !reach.ready ? reach : undefined;
    this.host.reached(this.shown);
    clearTimeout(this.watching);
    if (this.shown === undefined) {
      return;
    }
    this.watching = setTimeout(() => {
      const client = this.host.connect();
      void (client ? readReach(client, { folder }) : Promise.resolve(undefined)).then((again) => this.report(again, folder));
    }, WATCH_MS);
  }

  /** Post a fix the service named, then look at the way every few seconds: once nothing stops OpenCode, it is started
   * when its place is still waiting. */
  private async fix(fix: ReachFix, folder: string): Promise<void> {
    const client = this.host.connect();
    if (!client) {
      this.host.warn("the Clank service does not run: `clank serve --background` starts it");
      return;
    }
    try {
      await applyFix(client, fix, this.host.newKey());
    } catch (error) {
      this.host.warn(`${fix.label}: ${words(error)}`);
      return;
    }
    this.host.info(`${fix.label}: asked of Clank. OpenCode starts once its way to the model works.`);
    for (let tries = 0; tries < FIXED_TRIES; tries++) {
      await delay(FIXED_MS);
      const reach = await readReach(client, { folder });
      if (reach && !reach.blocked) {
        this.report(reach, folder);
        if (this.place && !this.place.closed && !this.busy) {
          void this.start();
        }
        return;
      }
    }
  }

  /** `clank serve --background`, with the window's CLANK_HOME; the place says how it went. */
  private startService(say: (line: string) => void): void {
    say("starting the Clank service: clank serve --background");
    const child = spawn("clank", ["serve", "--background"], {
      env: { ...process.env, CLANK_HOME: this.host.home() },
      stdio: "ignore",
      windowsHide: true,
    });
    child.on("error", (error) => say(`\`clank\` did not start (${error.message}): run \`clank serve --background\` in a terminal`));
    child.on("exit", (code) => {
      if (code) {
        say(`\`clank serve --background\` ended with exit code ${code}: run it in a terminal to see why`);
      }
    });
  }
}
