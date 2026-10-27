// The model's readout in VS Code (design 0021 §3): the status bar item and the panel under the agent's terminal. The
// item says the speed, the context used and the phase, read every few seconds; the panel, a webview in a group of its
// own below the agent's (a quarter of the right column's height), draws the rows `core/readout.ts` makes, read once a
// second while it shows. A click on the item, or `Clank: Show the model's readout`, opens the panel or brings it
// forward; it opens by itself with the agent when `clank.readout.openWithAgent` is on. Its group is neither the files'
// nor counted when the agent's group is kept at the right edge (`isReadoutGroup`). When the agent starts afresh the
// panel is made again under its new terminal (`show(true)`), and the groups a reloaded window left empty are closed
// first (`closeEmptyGroups`): neither the terminal nor the panel is revived, so their places stayed, and the new
// terminal went into a corner of them (2026-10-25). While something stands in OpenCode's way to the model (design 0004
// §5, revised 2026-10-26, `core/reach.ts`), the item says so in its place, and a click runs its fix. One reading at a
// time, each within `READ_MS`: a slow service used to start a second loop of readings with each show of the panel.

import { randomBytes } from "node:crypto";

import * as vscode from "vscode";

import type { ClankClient } from "./core/client";
import { type Reach, reachStatus } from "./core/reach";
import { panelRows, type Readout, statusText } from "./core/readout";

export const READOUT = "clank.readout";
const PANEL_MS = 1000;
const STATUS_MS = 3000;
const READ_MS = 10_000; // a reading the service does not answer in this long is given up
const SHARE = 0.25; // of the right column's height

/** Whether an editor group holds only the readout (or nothing yet: the group made for it, before its panel opens). */
export function isReadoutGroup(group: vscode.TabGroup): boolean {
  return group.tabs.every((tab) => tab.input instanceof vscode.TabInputWebview && tab.input.viewType.endsWith(READOUT));
}

/** Close the editor groups that hold nothing, but the first: the files' place, left of the agent's, kept even empty
 * (closing it too left the agent and the readout alone in the window, the files then opened in the readout's group). */
export async function closeEmptyGroups(): Promise<void> {
  const empty = vscode.window.tabGroups.all.filter(
    (group) => group.tabs.length === 0 && group.viewColumn !== vscode.ViewColumn.One,
  );
  if (empty.length) {
    await vscode.window.tabGroups.close(empty, true);
  }
}

interface Layout {
  orientation: number;
  groups: Array<{ size?: number; groups?: Layout["groups"] }>;
}

/** The status bar item and the panel. */
export class ReadoutPanel implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private ready = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private stopped = false;
  private reading = false; // a reading is under way: another tick waits for its end
  private again = false; // and one was asked meanwhile
  private problem: Reach | undefined; // what stands in OpenCode's way to the model, said in the item's place
  /** The workspace of the window's folder, as the newest readout said (a job's end is said in its window). */
  workspace: string | undefined;
  arranging = false; // while the panel's group is made: the agent's group is not moved meanwhile

  constructor(
    private readonly extension: vscode.Uri,
    private readonly item: vscode.StatusBarItem,
    private readonly connect: () => ClankClient | undefined,
    private readonly focusGroup: (column: number) => Thenable<unknown>,
    private readonly session: () => string = () => "", // the agent panel's, when it shows one (else the newest)
  ) {}

  /** Read the readout from now on: every few seconds for the item, every second while the panel shows. */
  start(): void {
    void this.tick();
  }

  /** What stands in OpenCode's way to the model now (undefined: nothing): said by the item until it is gone. */
  reach(reach: Reach | undefined): void {
    this.problem = reach;
    void this.tick();
  }

  dispose(): void {
    this.stopped = true;
    clearTimeout(this.timer);
    this.panel?.dispose();
  }

  /** Open the panel under the agent's terminal, or bring it forward; `again` (the agent started afresh) makes it
   * again under the terminal now there. */
  async show(again = false): Promise<void> {
    if (this.panel && !again) {
      this.panel.reveal(undefined, true);
      return;
    }
    this.panel?.dispose();
    await closeEmptyGroups();
    const before = vscode.window.tabGroups.activeTabGroup.viewColumn;
    const agent = vscode.window.tabGroups.all.find((group) =>
      group.tabs.some((tab) => tab.input instanceof vscode.TabInputTerminal && tab.label.startsWith("OpenCode · ")),
    );
    this.arranging = true;
    try {
      if (agent) {
        await this.focusGroup(agent.viewColumn);
        await vscode.commands.executeCommand("workbench.action.newGroupBelow");
      }
      this.panel = await this.make();
      if (agent) {
        await this.shareOfColumn();
        await this.focusGroup(before);
      }
    } finally {
      this.arranging = false;
    }
    await this.tick();
  }

  private async make(): Promise<vscode.WebviewPanel> {
    const media = vscode.Uri.joinPath(this.extension, "media");
    const panel = vscode.window.createWebviewPanel(
      READOUT,
      "Clank · the model",
      { viewColumn: vscode.ViewColumn.Active, preserveFocus: true },
      { enableScripts: true, localResourceRoots: [media], retainContextWhenHidden: true },
    );
    panel.iconPath = new vscode.ThemeIcon("pulse");
    const webview = panel.webview;
    const template = new TextDecoder().decode(await vscode.workspace.fs.readFile(vscode.Uri.joinPath(media, "readout.html")));
    const nonce = randomBytes(16).toString("base64");
    const file = (name: string): string => webview.asWebviewUri(vscode.Uri.joinPath(media, name)).toString();
    this.ready = false;
    const theme = (): void => {
      const named = vscode.workspace.getConfiguration("clank").get<string>("agentPanel.theme") ?? "vscode";
      void webview.postMessage({ type: "theme", theme: named });
    };
    webview.onDidReceiveMessage((message: { type?: string }) => {
      if (message.type === "ready") {
        this.ready = true;
        theme(); // the agent panel's theme: the readout sits under it
        void this.tick();
      }
    });
    const watching = vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("clank.agentPanel.theme")) {
        theme();
      }
    });
    panel.onDidDispose(() => {
      watching.dispose();
      if (this.panel === panel) {
        this.panel = undefined; // not a newer panel, made again under a new terminal
        this.ready = false;
      }
    });
    webview.html = template
      .replaceAll("{{source}}", webview.cspSource)
      .replaceAll("{{nonce}}", nonce)
      .replace("{{tokens}}", file("tokens.css"))
      .replace("{{css}}", file("readout.css"))
      .replace("{{script}}", file("readout.js"));
    return panel;
  }

  /** The right column split: the agent's group three quarters, the readout's one. */
  private async shareOfColumn(): Promise<void> {
    const layout = (await vscode.commands.executeCommand("vscode.getEditorLayout")) as Layout | undefined;
    const column = layout?.groups[layout.groups.length - 1];
    if (!layout || layout.orientation !== 0 || column?.groups?.length !== 2) {
      return;
    }
    column.groups[0].size = 1 - SHARE;
    column.groups[1].size = SHARE;
    await vscode.commands.executeCommand("vscode.setEditorLayout", layout);
  }

  private async tick(): Promise<void> {
    if (this.reading) {
      this.again = true; // the reading under way schedules the next one, sooner
      return;
    }
    clearTimeout(this.timer);
    if (this.stopped) {
      return;
    }
    this.reading = true;
    try {
      const readout = await this.read();
      this.workspace = readout?.workspace ?? this.workspace;
      const problem = reachStatus(this.problem);
      this.item.text = problem?.text ?? statusText(readout);
      this.item.tooltip =
        problem?.tooltip ??
        (readout ? tooltip(readout) : "The Clank service does not answer, or this window has no folder.");
      this.item.command = problem ? "clank.checkReach" : "clank.showReadout";
      if (readout && this.panel && this.ready) {
        await this.panel.webview.postMessage({ type: "rows", rows: panelRows(readout) });
      }
    } finally {
      this.reading = false;
    }
    const soon = this.again;
    this.again = false;
    this.timer = setTimeout(() => void this.tick(), soon ? 0 : this.panel?.visible ? PANEL_MS : STATUS_MS);
  }

  private async read(): Promise<Readout | undefined> {
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const client = this.connect();
    if (!folder || !client) {
      return undefined;
    }
    try {
      return await client.within(READ_MS).get<Readout>("agents/readout", { folder, session: this.session() });
    } catch {
      return undefined; // a service from before the readout, or one that stopped: the item says so
    }
  }
}

function tooltip(readout: Readout): string {
  const rows = panelRows(readout);
  return [rows.title, rows.speed, rows.now, rows.context, rows.exact, rows.engine, rows.machine, rows.jobs,
    "Click: the panel."]
    .filter(Boolean)
    .join("\n");
}
