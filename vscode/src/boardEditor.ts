// The board editor in VS Code (design 0022 §1, §3, §5): a custom text editor for `*.board` files, so a board is a
// document of its own with VS Code's undo, redo and saving. Its page (media/board.*) draws the board and sends the
// owner's edits as operations; they are applied with the same core (`core/board.ts`), written to the document whole,
// and saved at once, so the service, which writes the agent's changes to the file, never meets an unsaved board. When
// the file changes (the agent's change, an undo, a redo) the page draws it again, and says when it was not the owner's
// own edit; a figure whose file a script writes again is drawn again too. Asking about a selection, filling a slot and
// sending the pins are messages to the agent's session (through the agent panel's way of sending); files dropped from
// the Explorer and images pasted become figures (a pasted image saved beside the board, in `board-media/`).

import { randomBytes } from "node:crypto";
import * as path from "node:path";

import * as vscode from "vscode";

import type { AgentApi } from "./core/agent";
import { applyOps, askMessage, type Board, type Drawing, Drawings, exportsToRedo, exportTarget, fillMessage, keptWith, type Op, parseBoard,
  pinsMessage, serializeBoard } from "./core/board";

export const BOARD_EDITOR = "clank.board";
const IMAGE = /\.(png|jpe?g|gif|webp|svg)$/i;
const MEDIA_FOLDER = "board-media";
const REDO_WAIT = 1500; // a kept export is made again this long after the owner's last edit
const FORMATS = [
  { label: "PDF", description: "for \\includegraphics in a paper: vector, its LaTeX typeset by TeX", format: "pdf" },
  { label: "PNG", description: "300 dpi, for slides and notes", format: "png" },
  { label: "SVG", description: "vector, for the web or another editor", format: "svg" },
];

/** What the service says of an export: the file, what was left out, and the export in words. */
interface Exported {
  file: string;
  problems: string[];
  said: string;
}

/** A kept export, as its frame remembers it. */
interface KeptExport {
  file: string;
  format: string;
  dpi: number;
}

/** What the editor needs of the rest of the extension. */
export interface BoardHost {
  tell(text: string): Promise<void>; // a message to the agent's session
  api(): AgentApi | undefined; // the service, when it runs
  info(text: string): void;
  warn(text: string): void;
}

interface Received {
  type: string;
  ops?: Op[];
  ids?: string[];
  id?: string;
  text?: string;
  uris?: string[];
  x?: number;
  y?: number;
  mime?: string;
  data?: string;
}

const EMPTY: Board = { board: 1, title: "", settings: { grid: 20, preamble: "" }, items: [] };

export class BoardEditor implements vscode.CustomTextEditorProvider {
  constructor(
    private readonly extension: vscode.Uri,
    private readonly host: BoardHost,
  ) {}

  static register(extension: vscode.Uri, host: BoardHost): vscode.Disposable {
    return vscode.window.registerCustomEditorProvider(BOARD_EDITOR, new BoardEditor(extension, host), {
      webviewOptions: { retainContextWhenHidden: true },
      supportsMultipleEditorsPerDocument: false,
    });
  }

  async resolveCustomTextEditor(document: vscode.TextDocument, panel: vscode.WebviewPanel): Promise<void> {
    const folder = vscode.workspace.getWorkspaceFolder(document.uri)?.uri ?? vscode.Uri.file(path.dirname(document.uri.fsPath));
    const media = vscode.Uri.joinPath(this.extension, "media");
    const out = vscode.Uri.joinPath(this.extension, "out");
    const webview = panel.webview;
    webview.options = { enableScripts: true, localResourceRoots: [media, out, folder] };
    const file = (...names: string[]): string => webview.asWebviewUri(vscode.Uri.joinPath(media, ...names)).toString();
    const nonce = randomBytes(16).toString("base64");
    const template = new TextDecoder().decode(await vscode.workspace.fs.readFile(vscode.Uri.joinPath(media, "board.html")));
    webview.html = template
      .replaceAll("{{source}}", webview.cspSource)
      .replaceAll("{{nonce}}", nonce)
      .replace("{{tokens}}", file("tokens.css"))
      .replace("{{css}}", file("board.css"))
      .replace("{{script}}", file("board.js"))
      .replace("{{core}}", webview.asWebviewUri(vscode.Uri.joinPath(out, "src", "core", "board.js")).toString())
      .replace("{{marked}}", file("lib", "marked.min.js"))
      .replace("{{katex}}", file("lib", "katex.min.js"))
      .replace("{{katexCss}}", file("lib", "katex.min.css"));

    const relative = (): string => vscode.workspace.asRelativePath(document.uri, false).replace(/\\/g, "/");
    const current = (): Board => {
      try {
        return parseBoard(document.getText());
      } catch {
        return EMPTY;
      }
    };
    const drawings = new Drawings();
    let workspace: string | undefined;
    let writing = 0; // the owner's own edits being written, which need no word
    let said = "";
    let posting: ReturnType<typeof setTimeout> | undefined;
    let seen = current(); // the board as last drawn
    let owners = false; // whether the change since is the owner's (the agent's makes its kept exports itself)
    const redoing = new Set<string>(); // kept frames to export again
    let redoTimer: ReturnType<typeof setTimeout> | undefined;
    const service = async (): Promise<{ api: AgentApi; workspace: string }> => {
      const api = this.host.api();
      if (!api) throw new Error("the Clank service does not run: `clank serve --background` starts it");
      workspace ??= (await api.get<{ workspace?: string }>("workspaces/folder", { folder: folder.fsPath })).workspace;
      if (!workspace) throw new Error("this folder is not one of Clank's workspaces yet: `clank code` here makes it one");
      return { api, workspace };
    };
    const exported = async (asked: Record<string, unknown>): Promise<Exported> => {
      const { api, workspace } = await service();
      return api.post<Exported>("agents/boards/export", { workspace, board: relative(), ...asked });
    };
    // Kept exports the owner's edit changed, made again a moment after the last edit (one export per frame).
    const redo = (frames: string[]): void => {
      for (const frame of frames) redoing.add(frame);
      if (!redoing.size) return;
      clearTimeout(redoTimer);
      redoTimer = setTimeout(() => {
        const board = current();
        for (const frame of [...redoing]) {
          redoing.delete(frame);
          const kept = board.items.find((each) => each.id === frame)?.export as KeptExport | undefined;
          if (!kept) continue;
          exported({ frame, format: kept.format, file: kept.file, dpi: kept.dpi }).then(
            (made) => void webview.postMessage({ type: "said", said: `Made ${made.file} again` }),
            (error: unknown) => this.host.warn(`${frame}'s export: ${error instanceof Error ? error.message : String(error)}`),
          );
        }
      }, REDO_WAIT);
    };
    const post = async (): Promise<void> => {
      let board: Board;
      try {
        board = parseBoard(document.getText());
      } catch (error) {
        void webview.postMessage({ type: "board", board: EMPTY, path: relative(),
          said: `This file is not a board Clank can read: ${error instanceof Error ? error.message : String(error)}` });  // prettier-ignore
        return;
      }
      const uris: Record<string, string> = {};
      for (const item of board.items) {
        if (item.kind !== "figure" || typeof item.file !== "string" || item.file in uris) continue;
        const target = vscode.Uri.joinPath(folder, ...item.file.split("/"));
        try {
          const stat = await vscode.workspace.fs.stat(target);
          uris[item.file] = `${webview.asWebviewUri(target).toString()}?v=${stat.mtime}`; // a figure written again is drawn again
        } catch {
          // not in the folder: the page says so
        }
      }
      for (const wanted of drawings.wanted(board)) void draw(wanted);
      void webview.postMessage({ type: "board", board, path: relative(), uris, said, compiled: drawings.shown(board) });
      said = "";
      if (owners) redo(exportsToRedo(seen, board));
      owners = false;
      seen = board;
    };
    // A compiled LaTeX item's drawing, built by the service in the folder's container; the page draws it inline (so
    // its black takes the board's text color) once it is here.
    const draw = async (wanted: { id: string; key: string }): Promise<void> => {
      let drawing: Drawing;
      try {
        const { api, workspace } = await service();
        const made = await api.post<{ file?: string; error?: string }>("agents/boards/latex", { workspace, board: relative(), id: wanted.id });
        const file = made.file ? vscode.Uri.joinPath(folder, ...made.file.split("/")) : undefined;
        drawing = file ? { svg: new TextDecoder().decode(await vscode.workspace.fs.readFile(file)) } : { error: made.error ?? "it did not build" };
      } catch (error) {
        drawing = { error: error instanceof Error ? error.message : String(error) };
      }
      drawings.answer(wanted.key, drawing);
      later();
    };
    const later = (wait = 40): void => {
      clearTimeout(posting);
      posting = setTimeout(() => void post(), wait);
    };
    const write = async (board: Board): Promise<void> => {
      writing++;
      try {
        const edit = new vscode.WorkspaceEdit();
        edit.replace(document.uri, new vscode.Range(0, 0, document.lineCount, 0), serializeBoard(board));
        await vscode.workspace.applyEdit(edit);
        await document.save();
      } finally {
        writing--;
      }
    };
    const theme = (): void => {
      void webview.postMessage({ type: "theme", theme: vscode.workspace.getConfiguration("clank").get<string>("agentPanel.theme") ?? "vscode" });
    };
    const figure = (target: vscode.Uri, x: number, y: number): void => {
      const inside = path.relative(folder.fsPath, target.fsPath);
      if (!IMAGE.test(target.fsPath) || inside.startsWith("..") || path.isAbsolute(inside)) {
        this.host.warn(`${path.basename(target.fsPath)} is not an image of this folder: a board shows the folder's images`);
        return;
      }
      void webview.postMessage({ type: "figure", file: inside.split(path.sep).join("/"), uri: webview.asWebviewUri(target).toString(), x, y });
    };

    const subscriptions: vscode.Disposable[] = [
      vscode.workspace.onDidChangeTextDocument((event) => {
        if (event.document !== document || !event.contentChanges.length) return;
        if (event.reason === vscode.TextDocumentChangeReason.Undo || event.reason === vscode.TextDocumentChangeReason.Redo) {
          void document.save();
          owners = true;
        } else if (!writing) {
          said = "Changed outside this editor: the agent's change, or another editor's";
        } else {
          owners = true;
        }
        later();
      }),
      vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration("clank.agentPanel.theme")) theme();
      }),
    ];
    const pictures = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, "**/*.{png,jpg,jpeg,gif,webp,svg}"));
    const changed = (uri: vscode.Uri): void => {
      const name = vscode.workspace.asRelativePath(uri, false).replace(/\\/g, "/");
      if (current().items.some((item) => item.kind === "figure" && (item.file === name || name.endsWith(`/${String(item.file)}`)))) later(300);
      redo(keptWith(current(), name)); // a script wrote a figure of a kept frame again
    };
    subscriptions.push(pictures, pictures.onDidChange(changed), pictures.onDidCreate(changed));

    webview.onDidReceiveMessage(async (message: Received) => {
      try {
        switch (message.type) {
          case "ready":
            theme();
            await post();
            break;
          case "ops":
            await write(applyOps(current(), message.ops ?? []));
            break;
          case "ask":
            await this.host.tell(askMessage(relative(), current(), message.ids ?? [], message.text ?? ""));
            break;
          case "fill": {
            const board = current();
            await write(applyOps(board, [{ op: "set", id: message.id ?? "", fields: { state: "filling" } }]));
            await this.host.tell(fillMessage(relative(), board, message.id ?? ""));
            break;
          }
          case "pins":
            await this.host.tell(pinsMessage(relative(), current()));
            this.host.info("the open pins went to the agent; it closes each one it deals with");
            break;
          case "drop":
            for (const each of message.uris ?? []) figure(vscode.Uri.parse(each), message.x ?? 0, message.y ?? 0);
            break;
          case "paste": {
            const kind = /^image\/(png|jpeg|gif|webp)$/.exec(message.mime ?? "")?.[1] ?? "png";
            const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..*$/, "").replace("T", "-");
            const target = vscode.Uri.joinPath(document.uri, "..", MEDIA_FOLDER, `pasted-${stamp}.${kind === "jpeg" ? "jpg" : kind}`);
            await vscode.workspace.fs.writeFile(target, Buffer.from(message.data ?? "", "base64"));
            figure(target, message.x ?? 0, message.y ?? 0);
            break;
          }
          case "export":
            await this.export(current(), message.ids ?? [], exported, folder);
            break;
        }
      } catch (error) {
        this.host.warn(error instanceof Error ? error.message : String(error));
      }
    });
    panel.onDidDispose(() => {
      clearTimeout(posting);
      clearTimeout(redoTimer);
      for (const each of subscriptions) each.dispose();
    });
  }

  /** Export (design 0022 §7): the frame chosen, the selection, or the frame asked for; as PDF, PNG or SVG; once, or
   * kept (made again each time the frame changes). The file opens beside the board when asked. */
  private async export(board: Board, selected: string[], exported: (asked: Record<string, unknown>) => Promise<Exported>,
    folder: vscode.Uri): Promise<void> {  // prettier-ignore
    const target = exportTarget(board, selected);
    const named = (id: string): string => String(board.items.find((each) => each.id === id)?.name ?? id);
    let frame = target.frame;
    if (target.frames) {
      const picked = await vscode.window.showQuickPick(target.frames.map((id) => ({ label: named(id), description: id, id })),
        { title: "Export which frame?" });  // prettier-ignore
      if (!picked) return;
      frame = picked.id;
    }
    const format = await vscode.window.showQuickPick(FORMATS, { title: frame ? `Export ${named(frame)} as` : "Export the selection as" });
    if (!format) return;
    let keep: boolean | undefined;
    if (frame) {
      const how = await vscode.window.showQuickPick(
        [{ label: "Once", keep: false }, { label: "Keep it exported", description: "made again each time the frame changes", keep: true }],
        { title: `Export ${named(frame)}` },
      );  // prettier-ignore
      if (!how) return;
      keep = how.keep;
    }
    const made = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `Exporting ${frame ? named(frame) : "the selection"}…` },
      () => exported(frame ? { frame, format: format.format, keep } : { ids: target.ids ?? [], format: format.format }),
    );
    const open = await vscode.window.showInformationMessage(made.said, "Open");
    if (open) {
      await vscode.commands.executeCommand("vscode.open", vscode.Uri.joinPath(folder, ...made.file.split("/")), { viewColumn: vscode.ViewColumn.Beside });
    }
  }
}

/** `Clank: New board`: a board in the window's folder (named, in a subfolder if the name has one), opened. */
export async function newBoard(warn: (text: string) => void): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri;
  if (!folder) {
    warn("open a folder first: a board is a file of the folder");
    return;
  }
  const name = await vscode.window.showInputBox({
    title: "A new board", prompt: "Its name, or a path in the folder (figures/fig3)", value: "board",
    validateInput: (value) => (/^[\w./ -]+$/.test(value.trim()) && !value.includes("..") ? undefined : "letters, digits, -, _ and /"),
  });  // prettier-ignore
  if (!name?.trim()) return;
  const relative = name.trim().replace(/\.board$/, "");
  const target = vscode.Uri.joinPath(folder, ...`${relative}.board`.split("/"));
  try {
    await vscode.workspace.fs.stat(target);
  } catch {
    const title = path.basename(relative);
    await vscode.workspace.fs.writeFile(target, Buffer.from(serializeBoard({ ...EMPTY, title })));
  }
  await vscode.commands.executeCommand("vscode.openWith", target, BOARD_EDITOR);
}
