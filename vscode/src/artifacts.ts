// Artifacts in VS Code (design 0021 §5): a webview panel per artifact, in the files' group, showing a version as
// `core/artifacts.ts` writes the panel (Clank's bar over the page, which runs in a sandboxed frame, decision 0165). The
// page is the service's (`GET agents/artifacts/{workspace}/{name}/page`), built whole with its files and libraries, so
// the panel loads nothing from disk. The bar's version shows that version; Comment asks for the owner's words and sends
// them to the session that made it; Open in browser asks the owner first, in VS Code's own question
// (`BrowserQuestions`, decision 0156), then has the service export the version as one page and opens it. `Clank: Open
// an artifact` lists the folder's.

import * as vscode from "vscode";

import type { ClankClient } from "./core/client";
import { type ArtifactMade, artifactPanel, type ArtifactShown, BrowserQuestions, versionsSaid } from "./core/artifacts";

export const ARTIFACT = "clank.artifact";

/** An open artifact's panel: what it shows, and the questions it asks before a browser opens. */
interface Open {
  panel: vscode.WebviewPanel;
  made: ArtifactMade;
  shown: number;
  questions: BrowserQuestions;
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
  private readonly open = new Map<string, Open>();

  constructor(private readonly host: ArtifactHost) {}

  dispose(): void {
    for (const each of this.open.values()) {
      each.panel.dispose();
    }
  }

  /** Show an artifact's version (its newest by default) in its panel, made when it is not open. */
  async show(made: ArtifactMade, version?: number): Promise<void> {
    const client = this.host.connect();
    if (!client) {
      this.host.warn("the Clank service does not run: `clank serve --background` starts it");
      return;
    }
    let shown: ArtifactShown;
    try {
      shown = await client.get<ArtifactShown>(`${route(made)}/page`, { version });
    } catch (error) {
      this.host.warn(`the artifact ${made.name} cannot be shown: ${error instanceof Error ? error.message : String(error)}`);
      return;
    }
    const key = `${made.folder}|${made.name}`;
    let open = this.open.get(key);
    if (!open) {
      const panel = vscode.window.createWebviewPanel(
        ARTIFACT,
        `Artifact: ${shown.title}`,
        { viewColumn: this.host.column(), preserveFocus: true },
        { enableScripts: true, enableForms: false, localResourceRoots: [], retainContextWhenHidden: true },
      );
      panel.iconPath = new vscode.ThemeIcon("graph");
      open = { panel, made, shown: shown.version, questions: new BrowserQuestions() };
      this.open.set(key, open);
      const opened = open;
      panel.onDidDispose(() => this.open.delete(key));
      panel.webview.onDidReceiveMessage((message: { type?: string; version?: number }) =>
        void this.received(opened, message),
      );
    }
    open.made = { ...open.made, title: shown.title };
    open.shown = shown.version;
    open.panel.webview.html = artifactPanel(shown.html, shown.title, versionsSaid(shown.versions, shown.version));
    open.panel.title = `Artifact: ${shown.title} (v${shown.version})`;
    open.panel.reveal(undefined, true);
  }

  private async received(open: Open, message: { type?: string; version?: number }): Promise<void> {
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
    const path = route(made);
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
        const version = open.shown;
        await open.questions.open(made.title, made.name, version, {
          confirm: (question, detail, button) =>
            Promise.resolve(vscode.window.showWarningMessage(question, { modal: true, detail }, button)),
          exported: async () => (await client.post<{ file: string }>(`${path}/export`, { version })).file,
          open: (file) => Promise.resolve(vscode.env.openExternal(vscode.Uri.file(file))),
        });
      }
    } catch (error) {
      this.host.warn(error instanceof Error ? error.message : String(error));
    }
  }
}

/** The service's route of an artifact. */
function route(made: ArtifactMade): string {
  return `agents/artifacts/${encodeURIComponent(made.workspace)}/${encodeURIComponent(made.name)}`;
}
