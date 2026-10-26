// The Clank extension's entry point: the thin glue between VS Code and the controller (design 0002 §3.2, M0.6). It
// makes the two status bar items (a click on Clank's answers the questions waiting, else switches the model), registers
// the commands, shows questions and picks with VS Code's own UI, and tells the controller when the user types. In
// Clank's VS Code window (design 0004 §5; the setting `clank.agent.openOnStart`) it starts the agent in a terminal
// beside the files when the window opens, trying again while the service does not answer yet; `clank.openAgent` does
// it on demand. The agent's changes (design 0007 §6): a change waiting for review opens as a diff in the editor group of
// the files (never over the agent's terminal), with Accept and Reject in its title bar; one made in auto mode opens as a
// preview; the mode's item shows plan, review or auto and a click picks one. A plan open in the editor (design 0009 §7)
// has Implement buttons above it that hand it to the agent. Completion (design 0006 §5): an inline completion
// provider for files, asking the gateway once typing stops; its item says whether it is on and served, and a click
// turns it off or on. A figure (PNG, JPEG) opens in Clank's annotator (`figures.ts`, design 0008): marks drawn on it
// and a message, sent to the workspace's agent. The Notion changes (design 0010 §6, `notion.ts`): a view of the
// batches the agent proposes for Notion, the count waiting in the status bar, and the review page of a batch, to
// approve what is checked or reject it. A flow's gate (design 0013 §10, `core/gates.ts`): a notification with its
// answers, Open (the file in the editor group of the files; its save tells the gates) and Diff (two tries' copies as
// `clank-flow:` documents in VS Code's diff, closed when the gate is settled), an answer's words asked in an input box.
// The files the agent opens for the owner (design 0018 §7, `core/show.ts`) open in the editor group of the files, the
// keyboard left with the agent, each as VS Code opens its kind (a figure in the annotator); a path the agent prints
// under `/workspace/` is a link in its terminal, opened the same way. "Annotate this PDF" (design 0020 §10,
// `core/pdf.ts`): its pages rendered by the service, the one picked opened in the annotator beside the agent. Comments
// for the agent on lines of .tex files (design 0020 §11, `comments.ts`), sent together. The model's readout (design
// 0021 §3, `readout.ts`): its speed, context and phase in the status bar, and a panel under the agent's terminal.
// Everything else is in `core/`, which is tested without VS Code. What the status bar shows is returned from
// `activate`, for the suite that runs inside VS Code (decision 0029).

import { existsSync } from "node:fs";
import { homedir } from "node:os";

import * as vscode from "vscode";

import { agentStart, agentTerminalOpen, rightward, type AgentStart } from "./core/agent";
import { ClankClient, NotRunning } from "./core/client";
import { Completer, type CompletionPresenter } from "./core/completion";
import { clankHome, readConnection } from "./core/connection";
import { Controller } from "./core/controller";
import { type GateAction, type GateButton, type GatePresenter, Gates, type Side } from "./core/gates";
import type { Question } from "./core/kinds";
import type { Choice, Presenter } from "./core/presenter";
import { AgentPanel } from "./agentPanel";
import { ArtifactPanels } from "./artifacts";
import { BoardEditor, newBoard } from "./boardEditor";
import type { ArtifactMade } from "./core/artifacts";
import { FIGURE_EDITOR, FigureEditor } from "./figures";
import { closeEmptyGroups, isReadoutGroup, ReadoutPanel } from "./readout";
import { implement, type ImplementMode, type ImplementPresenter, lenses, planPath, relativePlan } from "./core/plans";
import { NotionReviews, type TreeNode } from "./core/notion";
import { type ChangeView, type ReviewPresenter, Reviews } from "./core/review";
import { LatexComments } from "./comments";
import { pageToMark } from "./core/pdf";
import { containerLinks, sameFolder, type Shown } from "./core/show";
import { NOTION_VIEW, type NotionActions, NotionPage, NotionTree, VsCodeNotionPresenter } from "./notion";

const AGENT_TERMINAL = "OpenCode · "; // the names of the agent's terminals start with this (core/agent.ts)

/** The folder a Markdown file is in, when it may be a plan by its path: the workspace folder and the path in it. */
function planLocation(document: vscode.TextDocument): { folder: string; relative: string } | undefined {
  const folder = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath;
  const relative = folder ? relativePlan(document.uri.fsPath, folder, process.platform === "win32") : undefined;
  return folder && relative !== undefined && planPath(relative) ? { folder, relative } : undefined;
}

/** The Implement buttons on a plan open in the editor. */
class PlanLenses implements vscode.CodeLensProvider {
  provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
    if (!planLocation(document)) {
      return [];
    }
    const top = new vscode.Range(0, 0, 0, 0);
    return lenses(document.getText()).map(
      (lens) => new vscode.CodeLens(top, { title: lens.title, command: lens.command, arguments: [document.uri] }),
    );
  }
}

/** VS Code, as handing a plan to the agent sees it. */
function implementPresenter(
  document: vscode.TextDocument,
  base: VsCodePresenter,
  openAgent: () => Promise<void>,
): ImplementPresenter {
  return {
    save: async () => {
      if (document.isDirty) {
        await document.save();
      }
    },
    reveal: () => vscode.window.terminals.find((each) => each.name.startsWith(AGENT_TERMINAL))?.show(true),
    openAgent,
    offer: async (text, button) => (await vscode.window.showWarningMessage(`Clank: ${text}`, button)) === button,
    info: (text) => base.info(text),
    warn: (text) => base.warn(text),
    wait: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  };
}

/** The presenter, with VS Code's status bar, notifications and quick picks. */
class VsCodePresenter implements Presenter {
  /** The artifacts' panels (design 0021 §5), given once they are made. */
  artifacts: ArtifactPanels | undefined;

  constructor(
    private readonly clankItem: vscode.StatusBarItem,
    private readonly dockerItem: vscode.StatusBarItem,
  ) {}

  clank(text: string, tooltip: string): void {
    this.clankItem.text = text;
    this.clankItem.tooltip = tooltip;
  }

  docker(text: string, tooltip: string): void {
    this.dockerItem.text = text;
    this.dockerItem.tooltip = tooltip;
  }

  async ask(question: Question): Promise<string | undefined> {
    const labels = question.options.map((option) => option.label);
    const message = question.detail ? `${question.title} ${question.detail}` : question.title;
    const chosen = await vscode.window.showInformationMessage(`Clank: ${message}`, ...labels);
    return question.options.find((option) => option.label === chosen)?.id;
  }

  async pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined> {
    const chosen = await vscode.window.showQuickPick(
      items.map((item) => ({ label: item.label, detail: item.detail, value: item.value })),
      { placeHolder: placeholder },
    );
    return chosen?.value;
  }

  info(text: string): void {
    void vscode.window.showInformationMessage(`Clank: ${text}`);
  }

  warn(text: string): void {
    void vscode.window.showWarningMessage(`Clank: ${text}`);
  }

  async showFiles(found: Shown): Promise<void> {
    const windows = process.platform === "win32";
    const folder = vscode.workspace.workspaceFolders?.find((each) => sameFolder(each.uri.fsPath, found.folder, windows));
    if (!folder) {
      return; // another window's folder
    }
    for (const file of found.files) {
      await openBeside(vscode.Uri.joinPath(folder.uri, ...file.split("/")), (text) => this.warn(text));
    }
    const what = found.files.join(", ");
    vscode.window.setStatusBarMessage(`$(eye) The agent opened ${what}${found.why ? `: ${found.why}` : ""}`, 15_000);
  }

  async openArtifact(made: ArtifactMade): Promise<void> {
    const windows = process.platform === "win32";
    if (vscode.workspace.workspaceFolders?.some((each) => sameFolder(each.uri.fsPath, made.folder, windows))) {
      await this.artifacts?.show(made, made.version); // only in a window on its folder
    }
  }
}

/** A file opened for the owner to look at: in the editor group of the files, in its own tab, the keyboard left where it
 * was (with the agent), as VS Code opens its kind (a figure in Clank's annotator, a PDF in the PDF viewer). */
async function openBeside(file: vscode.Uri, warn: (text: string) => void): Promise<void> {
  try {
    await vscode.commands.executeCommand("vscode.open", file, {
      viewColumn: filesColumn(),
      preserveFocus: true,
      preview: false,
    });
  } catch (error) {
    warn(`${file.fsPath} did not open: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/** `Clank: Open an artifact`: the window's folder's artifacts, the newest first, the one picked opened. */
async function openArtifact(
  connect: () => ClankClient | undefined,
  presenter: VsCodePresenter,
  artifacts: ArtifactPanels,
  readout: ReadoutPanel,
): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const client = connect();
  const workspace = readout.workspace;
  if (!folder || !client || !workspace) {
    presenter.warn("open a folder whose Clank workspace runs, with the Clank service running");
    return;
  }
  try {
    const found = await client.get<{ artifacts: Array<{ name: string; title: string; kind: string; versions: number }> }>(
      "agents/artifacts",
      { workspace },
    );
    const chosen = await presenter.pick(
      found.artifacts.map((each) => ({
        label: each.title, detail: `${each.name} · ${each.kind} · ${each.versions} version(s)`, value: each,
      })),
      found.artifacts.length ? "Open an artifact" : "No artifact in this folder yet",
    );
    if (chosen) {
      await artifacts.show({ workspace, folder, name: chosen.name, title: chosen.title, kind: chosen.kind,
                             version: chosen.versions, entry: "" });  // prettier-ignore
    }
  } catch (error) {
    presenter.warn(error instanceof Error ? error.message : String(error));
  }
}

/** "Annotate this PDF": the PDF named (else the one open), its pages rendered by the service, the page to mark up
 * opened in the annotator, in the editor group of the files. */
async function annotatePdf(
  uri: vscode.Uri | undefined,
  connect: () => ClankClient | undefined,
  presenter: VsCodePresenter,
): Promise<void> {
  const input = vscode.window.tabGroups.activeTabGroup.activeTab?.input;
  const open = input instanceof vscode.TabInputCustom || input instanceof vscode.TabInputText ? input.uri : undefined;
  const pdf = uri ?? open;
  const folder = pdf && vscode.workspace.getWorkspaceFolder(pdf);
  if (!pdf || !pdf.fsPath.toLowerCase().endsWith(".pdf") || !folder) {
    presenter.warn("pick a PDF of the folder open here (right-click it: Annotate this PDF with Clank)");
    return;
  }
  const client = connect();
  if (!client) {
    presenter.warn("the Clank service does not run: `clank serve --background` starts it");
    return;
  }
  const relative = vscode.workspace.asRelativePath(pdf, false).replace(/\\/g, "/");
  const found = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `Clank: rendering the pages of ${relative}` },
    () => pageToMark(client, folder.uri.fsPath, relative, (items, placeholder) => presenter.pick(items, placeholder)),
  );
  if (found === undefined) {
    return;
  }
  if ("error" in found) {
    presenter.warn(found.error);
    return;
  }
  const page = vscode.Uri.joinPath(folder.uri, ...found.image.split("/"));
  await vscode.commands.executeCommand("vscode.openWith", page, FIGURE_EDITOR, {
    viewColumn: filesColumn(),
    preview: false,
  });
}

/** A path under `/workspace/` the agent printed, as a link to the folder's file (design 0018 §7.3). */
interface ContainerPath extends vscode.TerminalLink {
  file: vscode.Uri;
}

/** The links in the agent's terminal to the files it names as its container sees them. */
class ContainerPaths implements vscode.TerminalLinkProvider<ContainerPath> {
  constructor(private readonly presenter: VsCodePresenter) {}

  provideTerminalLinks(context: vscode.TerminalLinkContext): ContainerPath[] {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder || !context.terminal.name.startsWith(AGENT_TERMINAL)) {
      return [];
    }
    return containerLinks(context.line).flatMap((link) => {
      const file = vscode.Uri.joinPath(folder.uri, ...link.relative.split("/"));
      return existsSync(file.fsPath)
        ? [{ startIndex: link.start, length: link.length, tooltip: `Open ${link.relative} beside the agent`, file }]
        : [];
    });
  }

  handleTerminalLink(link: ContainerPath): void {
    void openBeside(link.file, (text) => this.presenter.warn(text));
  }
}

const REVIEW = "clank-review"; // a change waiting for review: its tab has Accept and Reject
const CHANGED = "clank-change"; // a change made in auto mode, shown after

/** The texts of the changes shown, by their address (`clank-review:/QUESTION/before/FILE`, `.../after/FILE`). */
class ChangeTexts implements vscode.TextDocumentContentProvider {
  private readonly texts = new Map<string, string>();

  set(uri: vscode.Uri, text: string): void {
    this.texts.set(uri.toString(), text);
  }

  forget(uri: vscode.Uri): void {
    this.texts.delete(uri.toString());
  }

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.texts.get(uri.toString()) ?? "";
  }
}

function changeUri(scheme: string, key: string, side: "before" | "after", relative: string): vscode.Uri {
  return vscode.Uri.from({ scheme, path: `/${key}/${side}/${relative}` });
}

/** The question a tab of a change waiting for review answers. */
function questionOf(tab: vscode.Tab | undefined): string | undefined {
  const input = tab?.input;
  const uri =
    input instanceof vscode.TabInputTextDiff ? input.modified : input instanceof vscode.TabInputText ? input.uri : undefined;
  return uri?.scheme === REVIEW ? uri.path.split("/")[1] : undefined;
}

/** The editor group of the files: never the one of the agent's terminal (it sits beside the files), nor the
 * readout's under it. */
function filesColumn(): vscode.ViewColumn {
  const groups = vscode.window.tabGroups.all;
  const terminal = groups.find((group) => group.tabs.some((tab) => tab.input instanceof vscode.TabInputTerminal));
  const files = groups.find((group) => group !== terminal && !(group.tabs.length && isReadoutGroup(group)));
  if (files) {
    return files.viewColumn;
  }
  if (terminal) {
    return terminal.viewColumn === vscode.ViewColumn.One ? vscode.ViewColumn.Two : vscode.ViewColumn.One;
  }
  return vscode.ViewColumn.Active;
}

/** The review's presenter: the mode's item, the changes as diffs, the note of a reject. */
class VsCodeReviewPresenter implements ReviewPresenter {
  constructor(
    private readonly item: vscode.StatusBarItem,
    private readonly texts: ChangeTexts,
    private readonly base: VsCodePresenter,
  ) {}

  mode(text: string, tooltip: string, shown: boolean): void {
    this.item.text = text;
    this.item.tooltip = tooltip;
    if (shown) {
      this.item.show();
    } else {
      this.item.hide();
    }
  }

  review(change: ChangeView, question: string, title: string): void {
    const before = changeUri(REVIEW, question, "before", change.relative);
    const after = changeUri(REVIEW, question, "after", change.relative);
    this.texts.set(before, change.before ?? "");
    this.texts.set(after, change.after ?? change.diff);
    const shown = { preview: false, preserveFocus: true, viewColumn: filesColumn() };
    void vscode.commands.executeCommand("vscode.diff", before, after, title, shown);
  }

  reviewed(question: string): void {
    const tabs = vscode.window.tabGroups.all.flatMap((group) => group.tabs).filter((tab) => questionOf(tab) === question);
    if (tabs.length) {
      void vscode.window.tabGroups.close(tabs);
    }
  }

  openReviews(): string[] {
    const tabs = vscode.window.tabGroups.all.flatMap((group) => group.tabs);
    return [...new Set(tabs.map(questionOf).filter((id): id is string => id !== undefined))];
  }

  changed(change: ChangeView, title: string): void {
    const before = changeUri(CHANGED, change.id, "before", change.relative);
    const after = changeUri(CHANGED, change.id, "after", change.relative);
    this.texts.set(before, change.before ?? "");
    this.texts.set(after, change.made ?? change.after ?? change.diff);
    const shown = { preview: true, preserveFocus: true, viewColumn: filesColumn() };
    void vscode.commands.executeCommand("vscode.diff", before, after, title, shown);
  }

  note(): Promise<string | undefined> {
    return Promise.resolve(
      vscode.window.showInputBox({
        title: "Reject the change",
        prompt: "What should the agent know? Optional; Escape keeps the change waiting.",
        placeHolder: "For example: keep the old name",
      }),
    );
  }

  pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined> {
    return this.base.pick(items, placeholder);
  }

  info(text: string): void {
    this.base.info(text);
  }

  warn(text: string): void {
    this.base.warn(text);
  }
}

const FLOW = "clank-flow"; // a try's copy of a deliverable, in a gate's diff: `clank-flow:/QUESTION/KEY`

/** The question a tab of a gate's diff belongs to. */
function gateOf(tab: vscode.Tab): string | undefined {
  const input = tab.input;
  const uri = input instanceof vscode.TabInputTextDiff ? input.modified : undefined;
  return uri?.scheme === FLOW ? uri.path.split("/")[1] : undefined;
}

/** The gates' presenter: a gate as a notification with its buttons, a file opened, two tries diffed, words asked. */
class VsCodeGatePresenter implements GatePresenter {
  constructor(
    private readonly texts: ChangeTexts,
    private readonly base: VsCodePresenter,
  ) {}

  async gate(_question: string, text: string, buttons: GateButton[]): Promise<GateAction | undefined> {
    const chosen = await vscode.window.showInformationMessage(`Clank: ${text}`, ...buttons.map((each) => each.label));
    return buttons.find((each) => each.label === chosen)?.action;
  }

  async open(file: string, exists: boolean): Promise<void> {
    const uri = vscode.Uri.file(file);
    try {
      const document = await vscode.workspace.openTextDocument(exists ? uri : uri.with({ scheme: "untitled" }));
      await vscode.window.showTextDocument(document, { preview: false, viewColumn: filesColumn() });
    } catch (error) {
      this.base.warn(`${file} did not open: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  diff(question: string, before: Side, after: Side, title: string): void {
    const uri = (side: Side): vscode.Uri => vscode.Uri.from({ scheme: FLOW, path: `/${question}/${side.key}` });
    const [left, right] = [uri(before), uri(after)];
    this.texts.set(left, before.text);
    this.texts.set(right, after.text);
    const shown = { preview: false, preserveFocus: true, viewColumn: filesColumn() };
    void vscode.commands.executeCommand("vscode.diff", left, right, title, shown);
  }

  closeDiffs(question: string): void {
    const tabs = vscode.window.tabGroups.all.flatMap((group) => group.tabs).filter((tab) => gateOf(tab) === question);
    if (tabs.length) {
      void vscode.window.tabGroups.close(tabs);
    }
  }

  note(title: string, prompt: string): Promise<string | undefined> {
    return Promise.resolve(
      vscode.window.showInputBox({ title, prompt, placeHolder: "Optional; Escape keeps the gate waiting" }),
    );
  }

  pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined> {
    return this.base.pick(items, placeholder);
  }

  info(text: string): void {
    this.base.info(text);
  }

  warn(text: string): void {
    this.base.warn(text);
  }
}

/** Completion's presenter: its status bar item, and messages. */
class VsCodeCompletionPresenter implements CompletionPresenter {
  constructor(
    private readonly item: vscode.StatusBarItem,
    private readonly base: VsCodePresenter,
  ) {}

  completion(text: string, tooltip: string, shown: boolean): void {
    this.item.text = text;
    this.item.tooltip = tooltip;
    if (shown) {
      this.item.show();
    } else {
      this.item.hide();
    }
  }

  info(text: string): void {
    this.base.info(text);
  }

  warn(text: string): void {
    this.base.warn(text);
  }
}

/** Gray text after the cursor, from the completer. */
function inlineProvider(completer: Completer): vscode.InlineCompletionItemProvider {
  return {
    async provideInlineCompletionItems(document, position, context, token) {
      const editor = vscode.window.activeTextEditor;
      if (context.selectedCompletionInfo || (editor?.document === document && !editor.selection.isEmpty)) {
        return [];
      }
      const aborted = new AbortController();
      const listening = token.onCancellationRequested(() => aborted.abort());
      try {
        const read = (): { before: string; after: string } => {
          const text = document.getText().replace(/\r\n/g, "\n");
          const offset = document.getText(new vscode.Range(new vscode.Position(0, 0), position)).replace(/\r\n/g, "\n").length;
          return { before: text.slice(0, offset), after: text.slice(offset) };
        };
        const found = await completer.complete(read, () => token.isCancellationRequested, aborted.signal);
        return found ? [new vscode.InlineCompletionItem(found, new vscode.Range(position, position))] : [];
      } finally {
        listening.dispose();
      }
    },
  };
}

/** The question of the change a command is about: the tab it was clicked in, else the active tab. */
function reviewedBy(uri?: vscode.Uri): string | undefined {
  if (uri?.scheme === REVIEW) {
    return uri.path.split("/")[1];
  }
  return questionOf(vscode.window.tabGroups.activeTabGroup.activeTab);
}

const START_TRIES = 30; // when the window opens, the agent is tried this often, START_SECONDS apart
const START_SECONDS = 2;

/** Start the agent in a terminal beside the files, for the folder the window has open: false when the service does
 * not answer (said unless `quiet`), true otherwise (started, or what is missing said). */
async function startAgent(
  connect: () => ClankClient | undefined,
  presenter: VsCodePresenter,
  quiet: boolean,
  started?: () => void,
): Promise<boolean> {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!folder) {
    presenter.warn("open a folder first: the agent works in the folder the window has open");
    return true;
  }
  const notRunning = (): boolean => {
    if (!quiet) {
      presenter.warn("the Clank service does not run: `clank serve --background` starts it");
    }
    return false;
  };
  const client = connect();
  if (!client) {
    return notRunning();
  }
  let found: AgentStart;
  try {
    found = await agentStart(client, folder);
  } catch (error) {
    if (error instanceof NotRunning) {
      return notRunning();
    }
    presenter.warn(`the agent did not start: ${error instanceof Error ? error.message : String(error)}`);
    return true;
  }
  if ("problem" in found) {
    presenter.warn(`the agent is not started: ${found.problem}`);
    return true;
  }
  if (found.terminal.replaces) {
    // one OpenCode window per workspace: the service closed the others, so their tabs go too
    vscode.window.terminals.filter((each) => each.name.startsWith(AGENT_TERMINAL)).forEach((each) => each.dispose());
  }
  await closeEmptyGroups(); // a reloaded window's empty places, so the terminal goes beside the files
  const terminal = vscode.window.createTerminal({
    name: found.terminal.name,
    shellPath: found.terminal.program,
    shellArgs: found.terminal.args,
    location: { viewColumn: (vscode.window.tabGroups.all.length + 1) as vscode.ViewColumn }, // a group at the right edge
    // Never revived by VS Code: a revived terminal ran its saved command again, with a port another OpenCode had by
    // then, out of Clank's reach (2026-10-16). A reloaded window starts the agent afresh instead.
    isTransient: true,
  });
  terminal.show();
  started?.();
  return true;
}

/** When the window opens: start the agent, unless a terminal of it is already there (a window from before 0.6.1 keeps
 * it through a reload, its tab first), trying again every few seconds while the service does not answer. */
async function startOnOpen(start: () => Promise<boolean>): Promise<void> {
  for (let tries = 0; tries < START_TRIES; tries++) {
    const tabs = vscode.window.tabGroups.all.flatMap((group) => group.tabs);
    const restored = tabs.filter((tab) => tab.input instanceof vscode.TabInputTerminal).map((tab) => tab.label);
    if (agentTerminalOpen(vscode.window.terminals.map((terminal) => terminal.name), restored)) {
      return;
    }
    if (await start()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, START_SECONDS * 1000));
  }
}

const FOCUS_GROUP = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"].map(
  (nth) => `workbench.action.focus${nth}EditorGroup`,
);

/** The agent at the right edge of the editor area: its group moved there when it is not (a window from before, or a
 * group opened to its right), the keyboard given back to the group that had it. The readout's group under it (design
 * 0021 §3) is not counted, nor is anything moved while it is made. */
class AgentOnTheRight {
  private moving = false;

  constructor(private readonly arranging: () => boolean = () => false) {}

  async keep(): Promise<void> {
    if (this.arranging()) {
      return;
    }
    const groups = vscode.window.tabGroups.all.filter((group) => !isReadoutGroup(group));
    const agent = groups.find((group) =>
      group.tabs.some((tab) => tab.input instanceof vscode.TabInputTerminal && agentTerminalOpen([], [tab.label])),
    );
    if (this.moving || !agent || agent.viewColumn > FOCUS_GROUP.length) {
      return;
    }
    const active = vscode.window.tabGroups.activeTabGroup.viewColumn;
    const { moves, refocus } = rightward(groups.length, agent.viewColumn, active);
    if (moves === 0) {
      return;
    }
    this.moving = true;
    try {
      await vscode.commands.executeCommand(FOCUS_GROUP[agent.viewColumn - 1]);
      for (let step = 0; step < moves; step++) {
        await vscode.commands.executeCommand("workbench.action.moveActiveEditorGroupRight");
      }
      if (refocus !== undefined && refocus <= FOCUS_GROUP.length) {
        await vscode.commands.executeCommand(FOCUS_GROUP[refocus - 1]);
      }
    } finally {
      this.moving = false;
    }
  }
}

/** What the extension gives other code: what its status bar shows now. */
export interface ClankExtension {
  status(): { clank: string; docker: string };
}

/** Start the extension: the status bar items, the commands, and the controller following the service. */
export function activate(context: vscode.ExtensionContext): ClankExtension {
  const clankItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  clankItem.command = "clank.click";
  const dockerItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
  dockerItem.command = "clank.docker";
  const home = (): string =>
    clankHome(vscode.workspace.getConfiguration("clank").get<string>("home"), process.env, homedir());
  const connect = (): ClankClient | undefined => {
    const found = readConnection(home());
    return found ? new ClankClient(found.url, found.token) : undefined;
  };
  const presenter = new VsCodePresenter(clankItem, dockerItem);
  const artifacts = new ArtifactPanels(context.extensionUri, {
    connect, info: (text) => presenter.info(text), warn: (text) => presenter.warn(text), column: filesColumn,
  });
  presenter.artifacts = artifacts;
  const modeItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 98);
  modeItem.command = "clank.switchReview";
  const texts = new ChangeTexts();
  const reviews = new Reviews(new VsCodeReviewPresenter(modeItem, texts, presenter), {
    folders: () => (vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath),
    showInAuto: () => vscode.workspace.getConfiguration("clank").get<boolean>("changes.showInAuto") ?? true,
  });
  const completionItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 97);
  completionItem.command = "clank.toggleCompletion";
  const completer = new Completer(new VsCodeCompletionPresenter(completionItem, presenter));
  const notionTree = new NotionTree();
  const notionView = vscode.window.createTreeView(NOTION_VIEW, { treeDataProvider: notionTree, showCollapseAll: true });
  const notionItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 96);
  notionItem.command = "workbench.view.extension.clank-notion";
  const notionPage = new NotionPage(context.extensionUri, () => notionActions);
  const notion = new NotionReviews(new VsCodeNotionPresenter(notionView, notionTree, notionItem, notionPage, presenter));
  const gates = new Gates(new VsCodeGatePresenter(texts, presenter));
  const controller = new Controller(presenter, connect, {
    home: home(), reviews, completion: completer, notion, gates, workspace: () => readout.workspace,
  });
  const notionActions: NotionActions = {
    open: (opening) => controller.notion((each, api) => each.open(api, opening)),
    approve: (batch, parts) => controller.notion((each, api) => each.approve(api, batch, parts)),
    reject: (batch) => controller.notion((each, api) => each.reject(api, batch)),
    rows: (batch, everything) => controller.notion((each, api) => each.rows(api, batch, everything)),
    comment: (batch, place, text) => controller.notion((each, api) => each.comment(api, batch, place, text)),
    uncomment: (batch, comment) => controller.notion((each, api) => each.uncomment(api, batch, comment)),
    sendBack: (batch) => controller.notion((each, api) => each.sendBack(api, batch)),
  };
  const batchOf = (node?: TreeNode): string | undefined => node?.open?.batch;
  const handOver = async (uri: vscode.Uri | undefined, chosen: ImplementMode | "current"): Promise<void> => {
    const document = uri
      ? await vscode.workspace.openTextDocument(uri)
      : vscode.window.activeTextEditor?.document;
    const where = document && planLocation(document);
    const client = connect();
    if (!document || !where) {
      presenter.warn("open a plan first: a Markdown file whose header says `kind: plan`");
      return;
    }
    if (!client) {
      presenter.warn("the Clank service does not run: `clank serve --background` starts it");
      return;
    }
    const mode: ImplementMode = chosen === "current" ? (reviews.view?.mode ?? "review") : chosen;
    const opening = async (): Promise<void> => {
      await startAgent(connect, presenter, false, agentStarted);
    };
    await implement(
      client,
      implementPresenter(document, presenter, opening),
      { folder: where.folder, file: document.uri.fsPath, caseless: process.platform === "win32" },
      mode,
    );
  };
  const readoutItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 95);
  readoutItem.command = "clank.showReadout";
  const readout = new ReadoutPanel(
    context.extensionUri,
    readoutItem,
    connect,
    (column) => (column <= FOCUS_GROUP.length ? vscode.commands.executeCommand(FOCUS_GROUP[column - 1]) : Promise.resolve()),
    () => agentPanel.session(), // after a restart the service follows no session yet; the panel finds one
  );
  const agentPanel = new AgentPanel(context.extensionUri, {
    connect, info: (text) => presenter.info(text), warn: (text) => presenter.warn(text),
    pick: (items, placeholder) => presenter.pick(items, placeholder), openArtifact: (made) => artifacts.show(made, made.version),
    filesColumn,
  });  // prettier-ignore
  const setting = (name: string): boolean => vscode.workspace.getConfiguration("clank").get<boolean>(name) ?? true;
  const agentStarted = (): void => {
    if (setting("readout.openWithAgent")) {
      setTimeout(() => void readout.show(true), 1500); // once the agent's group is placed, under it
    }
    if (setting("agentPanel.openWithAgent")) {
      setTimeout(() => void agentPanel.show(false), 2500); // a tab beside the terminal, which stays in front
    }
  };
  const onTheRight = new AgentOnTheRight(() => readout.arranging);
  const latexComments = new LatexComments(connect, presenter);
  context.subscriptions.push(
    vscode.window.tabGroups.onDidChangeTabGroups((event) => {
      if (event.opened.length) {
        void onTheRight.keep();
      }
    }),
    clankItem,
    dockerItem,
    vscode.commands.registerCommand("clank.questions", () => controller.questions()),
    vscode.commands.registerCommand("clank.switchModel", () => controller.switchModel()),
    vscode.commands.registerCommand("clank.click", () => controller.clicked()),
    vscode.commands.registerCommand("clank.docker", () => controller.chooseDocker()),
    vscode.commands.registerCommand("clank.dockerStart", () => controller.docker("start")),
    vscode.commands.registerCommand("clank.dockerStop", () => controller.docker("stop")),
    vscode.commands.registerCommand("clank.reconnect", () => controller.reconnect()),
    vscode.commands.registerCommand("clank.openAgent", () => startAgent(connect, presenter, false, agentStarted)),
    vscode.commands.registerCommand("clank.showReadout", () => readout.show()),
    vscode.commands.registerCommand("clank.showAgentPanel", () => agentPanel.show()),
    agentPanel,
    BoardEditor.register(context.extensionUri, {
      tell: (text) => agentPanel.tell(text), api: () => connect(), info: (text) => presenter.info(text),
      warn: (text) => presenter.warn(text),
    }),
    vscode.commands.registerCommand("clank.newBoard", () => newBoard((text) => presenter.warn(text))),
    vscode.window.registerUriHandler({
      // vscode://clank.clank/agent-panel opens the agent panel in front (for scripts and Clank's other clients)
      handleUri: (uri) => (uri.path === "/agent-panel" ? agentPanel.show() : undefined),
    }),
    vscode.commands.registerCommand("clank.openArtifact", () => openArtifact(connect, presenter, artifacts, readout)),
    artifacts,
    readoutItem,
    readout,
    vscode.commands.registerCommand("clank.acceptChange", (uri?: vscode.Uri) => controller.acceptChange(reviewedBy(uri))),
    vscode.commands.registerCommand("clank.rejectChange", (uri?: vscode.Uri) => controller.rejectChange(reviewedBy(uri))),
    vscode.commands.registerCommand("clank.switchReview", () => controller.switchReview()),
    vscode.commands.registerCommand("clank.toggleCompletion", () => controller.toggleCompletion()),
    vscode.commands.registerCommand("clank.implementReview", (uri?: vscode.Uri) => handOver(uri, "review")),
    vscode.commands.registerCommand("clank.implementAuto", (uri?: vscode.Uri) => handOver(uri, "auto")),
    vscode.commands.registerCommand("clank.implementContinue", (uri?: vscode.Uri) => handOver(uri, "current")),
    vscode.languages.registerCodeLensProvider({ language: "markdown", scheme: "file" }, new PlanLenses()),
    notionTree,
    notionView,
    notionItem,
    notionPage,
    vscode.commands.registerCommand("clank.notion.open", (node?: TreeNode) =>
      node?.open ? notionActions.open(node.open) : vscode.commands.executeCommand("workbench.view.extension.clank-notion"),
    ),
    vscode.commands.registerCommand("clank.notion.approveAll", (node?: TreeNode) => {
      const batch = batchOf(node);
      return batch ? notionActions.approve(batch) : undefined;
    }),
    vscode.commands.registerCommand("clank.notion.reject", (node?: TreeNode) => {
      const batch = batchOf(node);
      return batch ? notionActions.reject(batch) : undefined;
    }),
    vscode.commands.registerCommand("clank.notion.refresh", () => controller.notion((each, api) => each.load(api))),
    vscode.window.registerCustomEditorProvider(
      FIGURE_EDITOR,
      new FigureEditor(context.extensionUri, (annotation) => controller.annotate(annotation)),
      { webviewOptions: { retainContextWhenHidden: true } },
    ),
    vscode.commands.registerCommand("clank.annotatePdf", (uri?: vscode.Uri) => annotatePdf(uri, connect, presenter)),
    latexComments,
    vscode.commands.registerCommand("clank.latexComment.save", (reply: vscode.CommentReply) => latexComments.save(reply)),
    vscode.commands.registerCommand("clank.latexComment.remove", (thread: vscode.CommentThread) =>
      latexComments.remove(thread),
    ),
    vscode.commands.registerCommand("clank.latexComments.send", () => latexComments.send()),
    vscode.commands.registerCommand("clank.annotateFigure", (uri?: vscode.Uri) => {
      const target = uri ?? vscode.window.activeTextEditor?.document.uri;
      return target ? vscode.commands.executeCommand("vscode.openWith", target, FIGURE_EDITOR) : undefined;
    }),
    vscode.languages.registerInlineCompletionItemProvider(
      [{ scheme: "file" }, { scheme: "untitled" }],
      inlineProvider(completer),
    ),
    completionItem,
    vscode.window.registerTerminalLinkProvider(new ContainerPaths(presenter)),
    vscode.workspace.registerTextDocumentContentProvider(REVIEW, texts),
    vscode.workspace.registerTextDocumentContentProvider(CHANGED, texts),
    vscode.workspace.registerTextDocumentContentProvider(FLOW, texts),
    vscode.workspace.onDidCloseTextDocument((document) => texts.forget(document.uri)),
    vscode.workspace.onDidSaveTextDocument((document) => void controller.saved(document.uri.fsPath)),
    modeItem,
    vscode.workspace.onDidChangeTextDocument(() => controller.typing()),
    { dispose: () => controller.stop() },
  );
  clankItem.show();
  dockerItem.show();
  readoutItem.show();
  controller.start();
  readout.start();
  if (vscode.workspace.getConfiguration("clank").get<boolean>("agent.openOnStart")) {
    void startOnOpen(() => startAgent(connect, presenter, true, agentStarted)).then(() => onTheRight.keep());
  } else {
    void onTheRight.keep();
  }
  return { status: () => ({ clank: clankItem.text, docker: dockerItem.text }) };
}

/** Nothing to do: what `activate` made is disposed with the extension's context. */
export function deactivate(): void {}
