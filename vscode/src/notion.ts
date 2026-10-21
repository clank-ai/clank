// The Notion changes in VS Code (design 0010 §6), the glue over `core/notion.ts`: the "Notion changes" view (a tree in
// its own place in the activity bar, its badge the count waiting), the status bar's item, and the review page
// (media/notion.html, one page for the batch shown, opened beside nothing: in the active editor group). The page sends
// what the owner does (approve the parts checked, reject, show every row, comment, take a comment back, send the batch
// back, open an entry in Notion); a link opens in
// the browser only when it is Notion's own (https://www.notion.so/...).

import { randomBytes } from "node:crypto";

import * as vscode from "vscode";

import type { NotionPresenter, NotionReview, Opening, Place, TreeNode } from "./core/notion";

export const NOTION_VIEW = "clank.notionChanges";
const PAGE = "clank.notionReview";
const ICONS: Record<TreeNode["icon"], [string, string | undefined]> = {
  batch: ["inbox", undefined],
  database: ["database", undefined],
  added: ["diff-added", "gitDecoration.addedResourceForeground"],
  changed: ["diff-modified", "gitDecoration.modifiedResourceForeground"],
  removed: ["diff-removed", "gitDecoration.deletedResourceForeground"],
  written: ["check", "gitDecoration.addedResourceForeground"],
  failed: ["warning", "list.warningForeground"],
  earlier: ["history", undefined],
  done: ["pass", undefined],
  rejected: ["circle-slash", undefined],
};

/** What the page sends. */
interface FromPage {
  type?: string;
  batch?: string;
  parts?: Record<string, string[]>;
  everything?: boolean;
  url?: string;
  proposal?: string;
  field?: string;
  block?: number;
  text?: string;
  comment?: string;
}

/** What the owner does from the view and the page, done by the extension. */
export interface NotionActions {
  open(opening: Opening): Promise<void>;
  approve(batch: string, parts?: Record<string, string[]>): Promise<void>;
  reject(batch: string): Promise<void>;
  rows(batch: string, everything: boolean): Promise<void>;
  comment(batch: string, place: Place, text: string): Promise<void>;
  uncomment(batch: string, comment: string): Promise<void>;
  sendBack(batch: string): Promise<void>;
}

/** The view's nodes, as VS Code's tree asks for them. */
export class NotionTree implements vscode.TreeDataProvider<TreeNode> {
  private nodes: TreeNode[] = [];
  private readonly changed = new vscode.EventEmitter<TreeNode | undefined>();
  readonly onDidChangeTreeData = this.changed.event;

  show(nodes: TreeNode[]): void {
    this.nodes = nodes;
    this.changed.fire(undefined);
  }

  getChildren(node?: TreeNode): TreeNode[] {
    return node ? node.children : this.nodes;
  }

  getTreeItem(node: TreeNode): vscode.TreeItem {
    const state = !node.children.length
      ? vscode.TreeItemCollapsibleState.None
      : node.expanded
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.Collapsed;
    const item = new vscode.TreeItem(node.label, state);
    item.id = node.id;
    item.description = node.description;
    item.tooltip = node.tooltip;
    item.contextValue = node.context;
    const [icon, color] = ICONS[node.icon];
    item.iconPath = new vscode.ThemeIcon(icon, color ? new vscode.ThemeColor(color) : undefined);
    if (node.open) {
      item.command = { command: "clank.notion.open", title: "Open the review", arguments: [node] };
    }
    return item;
  }

  dispose(): void {
    this.changed.dispose();
  }
}

/** The review page of one batch at a time. */
export class NotionPage {
  private panel: vscode.WebviewPanel | undefined;
  private shown: NotionReview | undefined;
  private ready = false;

  constructor(
    private readonly extension: vscode.Uri,
    private readonly actions: () => NotionActions,
  ) {}

  /** The batch the page shows, when it is open. */
  batch(): string | undefined {
    return this.panel ? this.shown?.batch.id : undefined;
  }

  async show(review: NotionReview, reveal: boolean): Promise<void> {
    this.shown = review;
    if (!this.panel) {
      if (!reveal) {
        return;
      }
      this.panel = await this.make();
    } else if (reveal) {
      this.panel.reveal(undefined, false);
    }
    this.panel.title = `Notion: ${review.batch.summary || review.batch.id}`;
    if (this.ready) {
      await this.panel.webview.postMessage({ type: "review", review });
    }
  }

  dispose(): void {
    this.panel?.dispose();
  }

  private async make(): Promise<vscode.WebviewPanel> {
    const media = vscode.Uri.joinPath(this.extension, "media");
    const panel = vscode.window.createWebviewPanel(PAGE, "Notion changes", vscode.ViewColumn.Active, {
      enableScripts: true,
      localResourceRoots: [media],
      retainContextWhenHidden: true,
    });
    panel.iconPath = new vscode.ThemeIcon("database");
    const webview = panel.webview;
    const template = new TextDecoder().decode(await vscode.workspace.fs.readFile(vscode.Uri.joinPath(media, "notion.html")));
    const nonce = randomBytes(16).toString("base64");
    const file = (name: string): string => webview.asWebviewUri(vscode.Uri.joinPath(media, name)).toString();
    this.ready = false;
    webview.onDidReceiveMessage((message: FromPage) => void this.received(message));
    panel.onDidDispose(() => {
      this.panel = undefined;
      this.ready = false;
    });
    webview.html = template
      .replaceAll("{{source}}", webview.cspSource)
      .replaceAll("{{nonce}}", nonce)
      .replace("{{css}}", file("notion.css"))
      .replace("{{script}}", file("notion.js"));
    return panel;
  }

  private async received(message: FromPage): Promise<void> {
    const actions = this.actions();
    if (message.type === "ready") {
      this.ready = true;
      if (this.shown) {
        await this.panel?.webview.postMessage({ type: "review", review: this.shown });
      }
    } else if (message.type === "approve" && message.batch) {
      await actions.approve(message.batch, message.parts ?? {});
    } else if (message.type === "reject" && message.batch) {
      await actions.reject(message.batch);
    } else if (message.type === "rows" && message.batch) {
      await actions.rows(message.batch, Boolean(message.everything));
    } else if (message.type === "comment" && message.batch && message.text) {
      const place: Place = {};
      if (message.proposal) {
        place.proposal = message.proposal;
      }
      if (message.field) {
        place.field = message.field;
      }
      if (typeof message.block === "number") {
        place.block = message.block;
      }
      await actions.comment(message.batch, place, message.text);
    } else if (message.type === "uncomment" && message.batch && message.comment) {
      await actions.uncomment(message.batch, message.comment);
    } else if (message.type === "sendBack" && message.batch) {
      await actions.sendBack(message.batch);
    } else if (message.type === "open" && message.url && notionLink(message.url)) {
      await vscode.env.openExternal(vscode.Uri.parse(message.url));
    }
  }
}

/** Whether an address is one of Notion's own pages. */
export function notionLink(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && (parsed.hostname === "notion.so" || parsed.hostname.endsWith(".notion.so"));
  } catch {
    return false;
  }
}

/** The Notion review's presenter: the view, its badge, the status bar's item, the page, and VS Code's prompts. */
export class VsCodeNotionPresenter implements NotionPresenter {
  constructor(
    private readonly view: vscode.TreeView<TreeNode>,
    private readonly nodes: NotionTree,
    private readonly item: vscode.StatusBarItem,
    private readonly page: NotionPage,
    private readonly messages: { info(text: string): void; warn(text: string): void },
  ) {}

  count(count: number, text: string, tooltip: string): void {
    this.view.badge = count ? { value: count, tooltip } : undefined;
    this.item.text = text;
    this.item.tooltip = tooltip;
    if (count) {
      this.item.show();
    } else {
      this.item.hide();
    }
  }

  tree(nodes: TreeNode[]): void {
    this.nodes.show(nodes);
  }

  review(review: NotionReview, reveal: boolean): void {
    void this.page.show(review, reveal);
  }

  reviewing(): string | undefined {
    return this.page.batch();
  }

  async reason(): Promise<string | undefined> {
    return vscode.window.showInputBox({
      title: "Reject the batch",
      prompt: "Why? The agent is told, and nothing of the batch is written.",
      placeHolder: "Not these papers: …",
      ignoreFocusOut: true,
    });
  }

  async confirm(text: string, action: string): Promise<boolean> {
    return (await vscode.window.showInformationMessage(text, { modal: true }, action)) === action;
  }

  info(text: string): void {
    this.messages.info(text);
  }

  warn(text: string): void {
    this.messages.warn(text);
  }
}
