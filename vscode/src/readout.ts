// The model's readout in VS Code (design 0021 §3): the status bar item and the panel under the agent's terminal. The
// item says the speed, the context used and the phase, read every few seconds; the panel, a webview in a group of its
// own below the agent's (a quarter of the right column's height), draws the rows `core/readout.ts` makes, read once a
// second while it shows. A click on the item, or `Clank: Show the model's readout`, opens the panel or brings it
// forward; it opens by itself with the agent when `clank.readout.openWithAgent` is on. Its group is neither the files'
// nor counted when the agent's group is kept at the right edge (`isReadoutGroup`).

import { randomBytes } from "node:crypto";

import * as vscode from "vscode";

import type { ClankClient } from "./core/client";
import { panelRows, type Readout, statusText } from "./core/readout";

export const READOUT = "clank.readout";
const PANEL_MS = 1000;
const STATUS_MS = 3000;
const SHARE = 0.25; // of the right column's height

/** Whether an editor group holds only the readout (or nothing yet: the group made for it, before its panel opens). */
export function isReadoutGroup(group: vscode.TabGroup): boolean {
  return group.tabs.every((tab) => tab.input instanceof vscode.TabInputWebview && tab.input.viewType.endsWith(READOUT));
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
  arranging = false; // while the panel's group is made: the agent's group is not moved meanwhile

  constructor(
    private readonly extension: vscode.Uri,
    private readonly item: vscode.StatusBarItem,
    private readonly connect: () => ClankClient | undefined,
    private readonly focusGroup: (column: number) => Thenable<unknown>,
  ) {}

  /** Read the readout from now on: every few seconds for the item, every second while the panel shows. */
  start(): void {
    void this.tick();
  }

  dispose(): void {
    this.stopped = true;
    clearTimeout(this.timer);
    this.panel?.dispose();
  }

  /** Open the panel under the agent's terminal, or bring it forward. */
  async show(): Promise<void> {
    if (this.panel) {
      this.panel.reveal(undefined, true);
      return;
    }
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
    webview.onDidReceiveMessage((message: { type?: string }) => {
      if (message.type === "ready") {
        this.ready = true;
        void this.tick();
      }
    });
    panel.onDidDispose(() => {
      this.panel = undefined;
      this.ready = false;
    });
    webview.html = template
      .replaceAll("{{source}}", webview.cspSource)
      .replaceAll("{{nonce}}", nonce)
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
    clearTimeout(this.timer);
    if (this.stopped) {
      return;
    }
    const readout = await this.read();
    this.item.text = statusText(readout);
    this.item.tooltip = readout ? tooltip(readout) : "The Clank service does not answer, or this window has no folder.";
    if (readout && this.panel && this.ready) {
      await this.panel.webview.postMessage({ type: "rows", rows: panelRows(readout) });
    }
    this.timer = setTimeout(() => void this.tick(), this.panel?.visible ? PANEL_MS : STATUS_MS);
  }

  private async read(): Promise<Readout | undefined> {
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const client = this.connect();
    if (!folder || !client) {
      return undefined;
    }
    try {
      return await client.get<Readout>("agents/readout", { folder });
    } catch {
      return undefined; // a service from before the readout, or one that stopped: the item says so
    }
  }
}

function tooltip(readout: Readout): string {
  const rows = panelRows(readout);
  return [rows.title, rows.speed, rows.now, rows.context, rows.exact, rows.engine, rows.machine, "Click: the panel."]
    .filter(Boolean)
    .join("\n");
}
