// Clank's figure annotator in VS Code (design 0008 §6): a custom editor for PNG and JPEG files that shows the
// annotator page (media/annotator.html) in a webview. It sends the page the figure as a data URL (so the page can draw
// the marked-up copy from it), again when the file changes on disk (the agent rendered it anew), and passes a send to
// the service with the folder the window has open around the figure; the page then says where it went or why not. A
// PDF's page Clank rendered (`.clank/latex/pages/`, design 0020 §10) is said to be one, so its tools for text show.

import { randomBytes } from "node:crypto";
import * as path from "node:path";

import * as vscode from "vscode";

import type { Annotation } from "./core/annotate";

export const FIGURE_EDITOR = "clank.figure";
const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg" };

interface FromPage {
  type?: string;
  marks?: unknown[];
  message?: string;
  image?: string;
}

/** The annotator, as a custom editor of images. */
export class FigureEditor implements vscode.CustomReadonlyEditorProvider {
  constructor(
    private readonly extension: vscode.Uri,
    private readonly send: (annotation: Annotation) => Promise<{ ok: boolean; text: string }>,
  ) {}

  openCustomDocument(uri: vscode.Uri): vscode.CustomDocument {
    return { uri, dispose: () => undefined };
  }

  async resolveCustomEditor(document: vscode.CustomDocument, panel: vscode.WebviewPanel): Promise<void> {
    const media = vscode.Uri.joinPath(this.extension, "media");
    const webview = panel.webview;
    webview.options = { enableScripts: true, localResourceRoots: [media] };
    const template = new TextDecoder().decode(await vscode.workspace.fs.readFile(vscode.Uri.joinPath(media, "annotator.html")));
    const nonce = randomBytes(16).toString("base64");
    const file = (name: string): string => webview.asWebviewUri(vscode.Uri.joinPath(media, name)).toString();
    webview.html = template
      .replaceAll("{{source}}", webview.cspSource)
      .replaceAll("{{nonce}}", nonce)
      .replace("{{css}}", file("annotator.css"))
      .replace("{{marks}}", file("marks.js"))
      .replace("{{script}}", file("annotator.js"));

    const figure = document.uri;
    const show = async (updated: boolean): Promise<void> => {
      const bytes = await vscode.workspace.fs.readFile(figure);
      const type = TYPES[path.extname(figure.fsPath).toLowerCase()] ?? "image/png";
      await webview.postMessage({
        type: "figure",
        src: `data:${type};base64,${Buffer.from(bytes).toString("base64")}`,
        name: vscode.workspace.asRelativePath(figure),
        updated,
        page: figure.fsPath.replace(/\\/g, "/").includes("/.clank/latex/pages/"),
      });
    };
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(vscode.Uri.joinPath(figure, ".."), path.basename(figure.fsPath)),
    );
    const again = (): void => void show(true).catch(() => undefined);
    watcher.onDidChange(again);
    watcher.onDidCreate(again);
    panel.onDidDispose(() => watcher.dispose());

    webview.onDidReceiveMessage(async (message: FromPage) => {
      if (message.type === "ready") {
        await show(false);
        return;
      }
      if (message.type !== "send") {
        return;
      }
      const folder = vscode.workspace.getWorkspaceFolder(figure)?.uri.fsPath;
      const result = folder
        ? await this.send({
            folder,
            figure: figure.fsPath,
            marks: message.marks ?? [],
            message: message.message ?? "",
            image: message.image ?? "",
          })
        : { ok: false, text: "Open the figure's folder in VS Code (its Clank workspace) to send it to the agent." };
      await webview.postMessage({ type: result.ok ? "sent" : "failed", text: result.text });
    });
  }
}
