// Comments for the agent on LaTeX files (design 0020 §11), in VS Code: a comment controller on every .tex file of the
// window's folder, where the owner adds a comment on a line or a selection (the gutter's +), replies to it, removes
// it, and sends every comment not sent yet with "Send comments to the agent" (`core/comments.ts`); each thread sent is
// labeled with the number the agent knows it by, collapsed, and kept until the owner removes it.

import * as vscode from "vscode";

import { type CommentThreadView, sendComments } from "./core/comments";
import type { Api } from "./core/controller";

export const LATEX_COMMENTS = "clank.latex";

/** The owner's comments on LaTeX files, for the agent. */
export class LatexComments implements vscode.Disposable {
  private readonly controller: vscode.CommentController;
  private readonly threads = new Set<vscode.CommentThread>();

  constructor(
    private readonly connect: () => Api | undefined,
    private readonly say: { info(text: string): void; warn(text: string): void },
  ) {
    this.controller = vscode.comments.createCommentController(LATEX_COMMENTS, "Clank: comments for the agent");
    this.controller.options = { prompt: "Comment for the agent", placeHolder: "What should the agent change here?" };
    this.controller.commentingRangeProvider = {
      provideCommentingRanges: (document) =>
        document.uri.fsPath.toLowerCase().endsWith(".tex") && vscode.workspace.getWorkspaceFolder(document.uri)
          ? [new vscode.Range(0, 0, Math.max(0, document.lineCount - 1), 0)]
          : [],
    };
  }

  /** A comment written in a thread (a new one, or a reply). */
  save(reply: vscode.CommentReply): void {
    const thread = reply.thread;
    const comment: vscode.Comment = {
      body: new vscode.MarkdownString(reply.text),
      mode: vscode.CommentMode.Preview,
      author: { name: "you" },
    };
    thread.comments = [...thread.comments, comment];
    thread.label = "for the agent: not sent yet";
    thread.contextValue = "draft";
    this.threads.add(thread);
  }

  /** A thread removed. */
  remove(thread: vscode.CommentThread): void {
    this.threads.delete(thread);
    thread.dispose();
  }

  /** Send every comment not sent yet, of the window's folder. */
  async send(): Promise<void> {
    const api = this.connect();
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!api || !folder) {
      this.say.warn("the Clank service does not run, or no folder is open: `clank serve --background` starts it");
      return;
    }
    const threads = [...this.threads];
    const views: CommentThreadView[] = await Promise.all(threads.map((thread) => this.view(thread)));
    const sent = await sendComments(api, folder.uri.fsPath, views);
    if ("error" in sent) {
      this.say.warn(sent.error);
      return;
    }
    for (const [index, number] of sent.numbered) {
      const thread = threads[index]!;
      thread.label = `sent to the agent as comment ${number}`;
      thread.contextValue = "sent";
      thread.collapsibleState = vscode.CommentThreadCollapsibleState.Collapsed;
    }
    this.say.info(`${sent.text}: it answers each by its number`);
  }

  private async view(thread: vscode.CommentThread): Promise<CommentThreadView> {
    const document = await vscode.workspace.openTextDocument(thread.uri);
    const range = thread.range ?? new vscode.Range(0, 0, 0, 0);
    const lines = new vscode.Range(range.start.line, 0, range.end.line, Number.MAX_SAFE_INTEGER);
    const covered = range.isEmpty ? document.getText(document.validateRange(lines)) : document.getText(range);
    return {
      file: vscode.workspace.asRelativePath(thread.uri, false).replace(/\\/g, "/"),
      start: range.start.line,
      end: range.end.line,
      text: covered.trim(),
      bodies: thread.comments.map((comment) =>
        typeof comment.body === "string" ? comment.body : comment.body.value,
      ),
      sent: thread.contextValue === "sent",
    };
  }

  dispose(): void {
    this.controller.dispose();
  }
}
