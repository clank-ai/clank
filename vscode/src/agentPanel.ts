// The agent panel in VS Code (design 0021 §4): a webview tab in the agent's group, beside OpenCode's terminal, on the
// same session. It reads `GET /agents/conversation` every two seconds while the session works and every eight while it
// does not, only while it shows, and sends the page the items `core/conversation.ts` makes (each text's math set aside,
// each image's address in the folder), with the older messages the owner asked for kept before the newest page. What
// the owner does comes back as messages: a message (to the session, or a new one after New), Sessions (pick another of
// the folder's), Stop and Compact (the Guide's), Terminal (the session shown in OpenCode's terminal), an answer to a
// permission or a question, an artifact or an image to open, the files @ lists, and an image pasted, saved in the
// folder's `.clank/pasted/` for the agent to look at.

import { randomBytes } from "node:crypto";
import * as path from "node:path";

import * as vscode from "vscode";

import type { ArtifactMade } from "./core/artifacts";
import type { ClankClient } from "./core/client";
import {
  type Block,
  blocks,
  type Conversation,
  conversationItems,
  type PageMessage,
  splitMath,
  waitingItems,
} from "./core/conversation";
import type { Choice } from "./core/presenter";
import { type FootLine, footLine, type Readout } from "./core/readout";

export const AGENT = "clank.agent";
const AGENT_TERMINAL = "OpenCode · ";
const BUSY_MS = 2000;
const IDLE_MS = 8000;
const PAGE = 30;
const PASTED = ".clank/pasted";
const SKIPPED = "{**/node_modules/**,**/.git/**,**/.clank/**,**/__pycache__/**}";

/** What the panel needs of the rest of the extension. */
export interface AgentHost {
  connect(): ClankClient | undefined;
  info(text: string): void;
  warn(text: string): void;
  pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined>;
  openArtifact(made: ArtifactMade): Promise<void>;
  filesColumn(): vscode.ViewColumn;
}

/** What the page is sent to draw. */
interface Drawn {
  title: string;
  subtitle?: string;
  state?: "working" | "idle" | "waiting" | "none";
  model?: string;
  foot?: FootLine | null;
  older?: boolean;
  blocks?: Block[];
  empty?: string;
}

interface Received {
  type: string;
  text?: string;
  act?: string;
  id?: string;
  reply?: string;
  answers?: string[][];
  name?: string;
  title?: string;
  version?: number;
  path?: string;
  query?: string;
  mime?: string;
  data?: string;
}

/** The agent's terminal, when one is open in this window. */
function agentTerminal(): vscode.Terminal | undefined {
  return vscode.window.terminals.find((each) => each.name.startsWith(AGENT_TERMINAL));
}

/** The column of the agent's group: the one with its terminal's tab. */
function agentColumn(): vscode.ViewColumn | undefined {
  return vscode.window.tabGroups.all.find((group) =>
    group.tabs.some((tab) => tab.input instanceof vscode.TabInputTerminal && tab.label.startsWith(AGENT_TERMINAL)),
  )?.viewColumn;
}

/** The panel. */
export class AgentPanel implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private reading = false;
  private conversation: Conversation | undefined;
  private pinned = ""; // a session the owner picked or started here; else the folder's newest
  private fresh = false; // the next message starts a new session
  private older: PageMessage[] = []; // older messages the owner asked for, before the newest page
  private cursor = ""; // the page before the oldest one read
  private sent = ""; // what was last sent to the page, so the same is not drawn again

  constructor(
    private readonly extension: vscode.Uri,
    private readonly host: AgentHost,
  ) {}

  dispose(): void {
    clearTimeout(this.timer);
    this.panel?.dispose();
  }

  /** The session the panel shows ("" before it has read one), for the readout to follow the same. */
  session(): string {
    return this.conversation?.session?.id ?? "";
  }

  /** Open the panel in the agent's group (else beside), or bring it forward; `focus` false leaves the keyboard where
   * it is and the agent's terminal in front. */
  async show(focus = true): Promise<void> {
    if (!this.panel) {
      this.panel = this.make(agentColumn() ?? vscode.ViewColumn.Beside, focus);
    } else {
      this.panel.reveal(undefined, !focus);
    }
    if (!focus) {
      agentTerminal()?.show(true); // the terminal stays in front of its group
    }
    await this.tick();
  }

  private folder(): string | undefined {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }

  private make(column: vscode.ViewColumn, focus: boolean): vscode.WebviewPanel {
    const media = vscode.Uri.joinPath(this.extension, "media");
    const folder = this.folder();
    const panel = vscode.window.createWebviewPanel(
      AGENT,
      "Clank · agent",
      { viewColumn: column, preserveFocus: !focus },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [media, ...(folder ? [vscode.Uri.file(folder)] : [])],
      },
    );
    panel.iconPath = new vscode.ThemeIcon("comment-discussion");
    const webview = panel.webview;
    const file = (...names: string[]): string => webview.asWebviewUri(vscode.Uri.joinPath(media, ...names)).toString();
    const nonce = randomBytes(16).toString("base64");
    void vscode.workspace.fs.readFile(vscode.Uri.joinPath(media, "agent.html")).then((bytes) => {
      webview.html = new TextDecoder()
        .decode(bytes)
        .replaceAll("{{source}}", webview.cspSource)
        .replaceAll("{{nonce}}", nonce)
        .replace("{{css}}", file("agent.css"))
        .replace("{{script}}", file("agent.js"))
        .replace("{{marked}}", file("lib", "marked.min.js"))
        .replace("{{katex}}", file("lib", "katex.min.js"))
        .replace("{{katexCss}}", file("lib", "katex.min.css"));
    });
    webview.onDidReceiveMessage((message: Received) => void this.received(message));
    panel.onDidChangeViewState(() => {
      if (panel.visible) {
        void this.tick();
      }
    });
    const watching = vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("clank.agentPanel.theme")) {
        this.theme();
      }
    });
    panel.onDidDispose(() => watching.dispose());
    panel.onDidDispose(() => {
      if (this.panel === panel) {
        this.panel = undefined;
        this.sent = "";
        clearTimeout(this.timer);
      }
    });
    return panel;
  }

  /** Read the conversation (and the model's readout, for the panel's foot) and draw it when it changed; again in a
   * while, while the panel shows. */
  private async tick(): Promise<void> {
    clearTimeout(this.timer);
    if (!this.panel || this.reading) {
      return;
    }
    this.reading = true;
    let busy = false;
    try {
      const folder = this.folder();
      const client = this.host.connect();
      if (!folder || !client) {
        this.draw({ title: "Clank", empty: folder ? "The Clank service does not run: `clank serve --background` starts it." : "Open a folder first." });
        return;
      }
      const found = await client.get<Conversation>("agents/conversation", { folder, session: this.pinned, limit: PAGE });
      if (found.session?.id !== this.conversation?.session?.id) {
        this.older = []; // another session: its own older messages
        this.cursor = found.next;
      } else if (!this.older.length) {
        this.cursor = found.next;
      }
      this.conversation = found;
      busy = Boolean(found.session?.busy);
      if (!found.workspace) {
        this.draw({ title: "Clank", empty: "This folder has no Clank workspace: open it with `clank code` first." });
        return;
      }
      let readout: Readout | undefined;
      try {
        readout = await client.get<Readout>("agents/readout", { folder, session: found.session?.id ?? "" });
      } catch {
        readout = undefined; // the foot is left out; the conversation still shows
      }
      const newest = new Set(found.messages.map((each) => each.info.id));
      const messages = [...this.older.filter((each) => !newest.has(each.info.id)), ...found.messages];
      const waiting = waitingItems(found.waiting);
      const state = waiting.length ? "waiting" : busy ? "working" : found.session ? "idle" : "none";
      const foot = readout ? footLine(readout) : null;
      const doing = state === "working" ? foot?.phase || "Working" : state === "waiting" ? "Waits for you" : state === "idle" ? "Idle" : "";
      this.draw({
        title: found.session ? found.session.title || "A session" : "A new conversation",
        subtitle: [doing, readout?.slot.title, found.workspace].filter(Boolean).join(" · "),
        state, model: readout?.slot.title ?? "", foot, older: Boolean(this.cursor),
        blocks: blocks([...conversationItems(messages), ...waiting]),
        empty: "Write to the agent to start a conversation in this folder.",
      });  // prettier-ignore
    } catch (error) {
      this.draw({ title: "Clank", empty: `The conversation cannot be read: ${error instanceof Error ? error.message : String(error)}` });
    } finally {
      this.reading = false;
      if (this.panel?.visible) {
        this.timer = setTimeout(() => void this.tick(), busy ? BUSY_MS : IDLE_MS);
      }
    }
  }

  private draw(shown: Drawn): void {
    const webview = this.panel?.webview;
    const folder = this.folder();
    if (!webview) {
      return;
    }
    const ready = (block: Block): unknown => {
      if (block.kind === "text") {
        return { ...block, split: splitMath(block.text) };
      }
      if (block.kind === "image" && folder) {
        const file = path.isAbsolute(block.path) ? block.path : path.join(folder, ...block.path.split("/"));
        return { ...block, src: webview.asWebviewUri(vscode.Uri.file(file)).toString() };
      }
      if (block.kind === "steps") {
        return { ...block, steps: block.steps.map(ready) };
      }
      return block;
    };
    const message = {
      type: "conversation", title: shown.title, subtitle: shown.subtitle ?? "", state: shown.state ?? "none",
      model: shown.model ?? "", foot: shown.foot ?? null, older: shown.older ?? false, empty: shown.empty ?? "",
      blocks: (shown.blocks ?? []).map(ready),
    };  // prettier-ignore
    const text = JSON.stringify(message);
    if (text !== this.sent) {
      this.sent = text;
      void webview.postMessage(message);
    }
  }

  /** Tell the page the theme the setting names (`clank.agentPanel.theme`: VS Code's, or one of Clank's). */
  private theme(): void {
    const theme = vscode.workspace.getConfiguration("clank").get<string>("agentPanel.theme") ?? "vscode";
    void this.panel?.webview.postMessage({ type: "theme", theme });
  }

  private async received(message: Received): Promise<void> {
    if (message.type === "ready") {
      this.sent = "";
      this.theme();
      await this.tick();
      return;
    }
    const client = this.host.connect();
    const folder = this.folder();
    if (!client || !folder) {
      this.host.warn("the Clank service does not run: `clank serve --background` starts it");
      return;
    }
    const found = this.conversation;
    const workspace = found?.workspace ?? "";
    const session = found?.session ?? null;
    try {
      switch (message.type) {
        case "send":
          await this.send(client, workspace, session, message.text ?? "");
          break;
        case "older":
          await this.readOlder(client, folder);
          break;
        case "act":
          await this.act(client, workspace, session, message.act ?? "");
          break;
        case "permission":
          if (session) {
            await client.post(`agents/permissions/${encodeURIComponent(workspace)}/${session.port}/${encodeURIComponent(message.id ?? "")}`,
                              { reply: message.reply });  // prettier-ignore
          }
          break;
        case "question":
          if (session) {
            await client.post(`agents/questions/${encodeURIComponent(workspace)}/${session.port}/${encodeURIComponent(message.id ?? "")}`,
                              { answers: message.answers ?? [] });  // prettier-ignore
          }
          break;
        case "artifact":
          await this.host.openArtifact({
            workspace, folder, name: message.name ?? "", title: message.title ?? message.name ?? "", kind: "html",
            version: message.version ?? 1, entry: "",
          });  // prettier-ignore
          break;
        case "image": {
          const file = path.join(folder, ...(message.path ?? "").split("/"));
          await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(file), this.host.filesColumn());
          break;
        }
        case "files":
          await this.files(message.query ?? "");
          break;
        case "paste":
          await this.paste(folder, message.mime ?? "image/png", message.data ?? "");
          break;
        case "pickImage":
          await this.pickImage(folder);
          break;
        case "open": {
          const file = path.join(folder, ...(message.path ?? "").split("/"));
          await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(file), this.host.filesColumn());
          break;
        }
      }
    } catch (error) {
      this.host.warn(error instanceof Error ? error.message : String(error));
    }
    if (["send", "act", "permission", "question"].includes(message.type)) {
      setTimeout(() => void this.tick(), 500);
    }
  }

  private async send(client: ClankClient, workspace: string, session: Conversation["session"], text: string): Promise<void> {
    if (!text.trim()) {
      return;
    }
    if (!workspace) {
      this.host.warn("this folder has no Clank workspace: open it with `clank code` first");
      return;
    }
    if (this.fresh || !session) {
      const title = text.split("\n")[0].slice(0, 60);
      const started = await client.post<{ port: number; session: string }>(
        `agents/sessions/${encodeURIComponent(workspace)}/start`, { text, title },
      );  // prettier-ignore
      this.pinned = started.session;
      this.fresh = false;
    } else {
      await client.post(`agents/sessions/${encodeURIComponent(workspace)}/${session.port}/${encodeURIComponent(session.id)}/message`,
                        { text });  // prettier-ignore
    }
    void this.panel?.webview.postMessage({ type: "sent" });
  }

  private async act(client: ClankClient, workspace: string, session: Conversation["session"], act: string): Promise<void> {
    const named = session ? `${encodeURIComponent(workspace)}/${encodeURIComponent(session.id)}` : "";
    if (act === "new") {
      this.fresh = true;
      this.host.info("the next message you send starts a new session");
    } else if (act === "sessions" && workspace) {
      const listed = await client.get<{ servers: Array<{ sessions: Array<{ id: string; title: string; updated?: number; status: string }> }> }>(
        "agents/sessions", { workspace },
      );  // prettier-ignore
      const sessions = listed.servers.flatMap((each) => each.sessions)
        .filter((each, index, all) => all.findIndex((other) => other.id === each.id) === index)
        .sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0));  // prettier-ignore
      const picked = await this.host.pick(
        sessions.map((each) => ({ label: each.title || each.id, detail: `${each.id} · ${each.status}`, value: each.id })),
        sessions.length ? "Show a session of this folder" : "No session in this folder yet",
      );
      if (picked) {
        this.pinned = picked;
        this.fresh = false;
      }
    } else if (!named) {
      this.host.warn("no session yet: write to the agent to start one");
    } else if (act === "stop") {
      await client.post(`agents/guide/${named}/stop`);
    } else if (act === "compact") {
      await client.post(`agents/guide/${named}/compact`);
    } else if (act === "terminal") {
      await client.post(`agents/sessions/${named}/terminal`);
      agentTerminal()?.show(false);
    }
  }

  private async readOlder(client: ClankClient, folder: string): Promise<void> {
    const session = this.conversation?.session;
    if (!session || !this.cursor) {
      return;
    }
    const found = await client.get<Conversation>("agents/conversation", {
      folder, session: session.id, limit: PAGE, before: this.cursor,
    });  // prettier-ignore
    this.older = [...found.messages, ...this.older];
    this.cursor = found.next;
    await this.tick();
  }

  private async files(query: string): Promise<void> {
    const safe = query.replace(/[^\w./-]/g, "");
    const found = await vscode.workspace.findFiles(safe ? `**/*${safe}*` : "**/*", SKIPPED, 40);
    const paths = found.map((uri) => vscode.workspace.asRelativePath(uri, false).replace(/\\/g, "/"))
      .sort((a, b) => a.length - b.length || a.localeCompare(b)).slice(0, 12);  // prettier-ignore
    void this.panel?.webview.postMessage({ type: "files", files: paths });
  }

  private async paste(folder: string, mime: string, data: string): Promise<void> {
    const kind = /^image\/(png|jpeg|gif|webp)$/.exec(mime)?.[1] ?? "png";
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..*$/, "").replace("T", "-");
    const name = `${stamp}.${kind === "jpeg" ? "jpg" : kind}`;
    const target = vscode.Uri.file(path.join(folder, ...PASTED.split("/"), name));
    await vscode.workspace.fs.writeFile(target, Buffer.from(data, "base64"));
    void this.panel?.webview.postMessage({ type: "insert", text: `/workspace/${PASTED}/${name} ` });
  }

  /** An image picked from the disk: one in the folder is named where it is, another is copied into `.clank/pasted/`
   * (the agent's container sees only the folder). */
  private async pickImage(folder: string): Promise<void> {
    const [picked] = (await vscode.window.showOpenDialog({
      canSelectMany: false, defaultUri: vscode.Uri.file(folder), openLabel: "Add for the agent",
      filters: { Images: ["png", "jpg", "jpeg", "gif", "webp", "svg"] },
    })) ?? [];  // prettier-ignore
    if (!picked) {
      return;
    }
    const inside = path.relative(folder, picked.fsPath);
    if (inside && !inside.startsWith("..") && !path.isAbsolute(inside)) {
      void this.panel?.webview.postMessage({ type: "insert", text: `/workspace/${inside.split(path.sep).join("/")} ` });
      return;
    }
    const name = `${new Date().toISOString().replace(/[-:]/g, "").replace(/\..*$/, "").replace("T", "-")}-${path.basename(picked.fsPath)}`;
    await vscode.workspace.fs.copy(picked, vscode.Uri.file(path.join(folder, ...PASTED.split("/"), name)), { overwrite: false });
    void this.panel?.webview.postMessage({ type: "insert", text: `/workspace/${PASTED}/${name} ` });
  }
}
