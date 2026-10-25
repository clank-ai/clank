// Artifacts in VS Code (design 0021 §5): a webview panel per artifact, in the files' group, showing a version's page as
// `core/artifacts.ts` makes it ready (Clank's policy, its <base>, the libraries' place, the bar). The bar's version
// shows that version; Comment asks for the owner's words and sends them to the session that made it; Open in browser
// has the service export the version as one page and opens it. `Clank: Open an artifact` lists the folder's.

import { randomBytes } from "node:crypto";
import { posix } from "node:path";

import * as vscode from "vscode";

import type { ClankClient } from "./core/client";
import { artifactBar, type ArtifactMade, artifactPage, versionsSaid } from "./core/artifacts";

export const ARTIFACT = "clank.artifact";

interface Kept {
  name: string;
  title: string;
  kind: string;
  versions: Array<{ version: number; entry: string }>;
}

/** What the panels need of the rest of the extension. */
export interface ArtifactHost {
  connect(): ClankClient | undefined;
  info(text: string): void;
  warn(text: string): void;
  column(): vscode.ViewColumn;
}

/** The open artifacts' panels, one per artifact. */
export class ArtifactPanels implements vscode.Disposable {
  private readonly open = new Map<string, { panel: vscode.WebviewPanel; made: ArtifactMade; shown: number }>();

  constructor(
    private readonly extension: vscode.Uri,
    private readonly host: ArtifactHost,
  ) {}

  dispose(): void {
    for (const each of this.open.values()) {
      each.panel.dispose();
    }
  }

  /** Show an artifact's version (its newest by default) in its panel, made when it is not open. */
  async show(made: ArtifactMade, version?: number): Promise<void> {
    const key = `${made.folder}|${made.name}`;
    const home = vscode.Uri.file(posix.join(made.folder.replace(/\\/g, "/"), ".clank", "artifacts", made.name));
    let kept: Kept;
    try {
      kept = JSON.parse(new TextDecoder().decode(await vscode.workspace.fs.readFile(vscode.Uri.joinPath(home, "artifact.json"))));
    } catch {
      this.host.warn(`the artifact ${made.name} cannot be read in ${made.folder}`);
      return;
    }
    const shown = version ?? kept.versions.length;
    const entry = kept.versions.find((each) => each.version === shown)?.entry;
    if (!entry) {
      return;
    }
    let open = this.open.get(key);
    if (!open) {
      const lib = vscode.Uri.joinPath(this.extension, "media", "lib");
      const panel = vscode.window.createWebviewPanel(
        ARTIFACT,
        `Artifact: ${kept.title}`,
        { viewColumn: this.host.column(), preserveFocus: true },
        { enableScripts: true, localResourceRoots: [home, lib], retainContextWhenHidden: true },
      );
      panel.iconPath = new vscode.ThemeIcon("graph");
      open = { panel, made: { ...made, title: kept.title }, shown };
      this.open.set(key, open);
      const opened = open;
      panel.onDidDispose(() => this.open.delete(key));
      panel.webview.onDidReceiveMessage((message: { type?: string; version?: number }) =>
        void this.received(opened, message),
      );
    }
    open.shown = shown;
    const webview = open.panel.webview;
    const page = new TextDecoder().decode(
      await vscode.workspace.fs.readFile(vscode.Uri.joinPath(home, `v${shown}`, ...entry.split("/"))),
    );
    const folder = posix.dirname(entry);
    const base = vscode.Uri.joinPath(home, `v${shown}`, ...(folder === "." ? [] : folder.split("/")));
    const nonce = randomBytes(16).toString("base64");
    webview.html = artifactPage(page, {
      base: `${webview.asWebviewUri(base).toString()}/`,
      lib: webview.asWebviewUri(vscode.Uri.joinPath(this.extension, "media", "lib")).toString(),
      source: webview.cspSource,
      nonce,
      bar: artifactBar(kept.title, versionsSaid(kept.versions.length, shown), nonce),
    });
    open.panel.title = `Artifact: ${kept.title} (v${shown})`;
    open.panel.reveal(undefined, true);
  }

  private async received(
    open: { panel: vscode.WebviewPanel; made: ArtifactMade; shown: number },
    message: { type?: string; version?: number },
  ): Promise<void> {
    const { made } = open;
    if (message.type === "version" && message.version) {
      await this.show(made, message.version);
      return;
    }
    const client = this.host.connect();
    if (!client) {
      this.host.warn("the Clank service does not run: `clank serve --background` starts it");
      return;
    }
    const path = `agents/artifacts/${encodeURIComponent(made.workspace)}/${encodeURIComponent(made.name)}`;
    try {
      if (message.type === "comment") {
        const text = await vscode.window.showInputBox({
          title: `A comment on ${made.title}, version ${open.shown}, for the agent`,
          prompt: "It goes to the session that made this version, which answers with a new one.",
          ignoreFocusOut: true,
        });
        if (text?.trim()) {
          const said = await client.post<{ said: string }>(`${path}/comment`, { version: open.shown, text });
          this.host.info(said.said);
        }
      } else if (message.type === "browser") {
        const done = await client.post<{ file: string }>(`${path}/export`, { version: open.shown });
        await vscode.env.openExternal(vscode.Uri.file(done.file));
      }
    } catch (error) {
      this.host.warn(error instanceof Error ? error.message : String(error));
    }
  }
}
