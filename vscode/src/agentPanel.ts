// The agent panel in VS Code (design 0021 §4): a webview tab in the agent's group, beside OpenCode's terminal, on the
// same session. While it shows, it follows the conversation stream (design 0023 §3, `GET /agents/conversation/stream`):
// a snapshot, then each change as the mirror hears it, and the model's readout each second while it works; the live
// state is `core/talking.ts`, and the page is drawn from it at most ten times a second with the items
// `core/conversation.ts` makes (each text's math set aside, each image's address in the folder), the older messages the
// owner asked for kept before the newest page. A message the owner sends shows at once as pending and the composer
// clears; when the send fails the text comes back. A stream that breaks is opened again with a growing wait, resuming
// from its version; after three failures in a row the panel falls back to reading the route every two seconds while
// the session works and every eight while it does not, and says so in its header. What the owner does comes back as
// messages: a message (to the session, or a new one after New), Sessions (pick another of the folder's), Stop and
// Compact (the Guide's), Terminal (the session shown in OpenCode's terminal), an answer to a permission or a question,
// an artifact or an image to open, the files @ lists, and an image pasted, saved in the folder's `.clank/pasted/` for
// the agent to look at. What stands in OpenCode's way to the model (design 0004 §5, revised 2026-10-26) shows as a line
// under the header, with the fix's button, until it is gone.

import { randomBytes } from "node:crypto";
import * as path from "node:path";

import * as vscode from "vscode";

import type { ArtifactMade } from "./core/artifacts";
import type { ClankClient } from "./core/client";
import { type Block, blocks, type Conversation, type PageMessage, splitMath, waitingItems } from "./core/conversation";
import type { Choice } from "./core/presenter";
import { headerLink, nextWait, pagesAfterSnapshot, pollsAfter, RETRY_MS, streamParameters } from "./core/following";
import { type FootLine, footLine, type Readout } from "./core/readout";
import { applyEvent, emptyTalk, failed, liveItems, sent, type Talk } from "./core/talking";

export const AGENT = "clank.agent";
const AGENT_TERMINAL = "OpenCode · ";
const BUSY_MS = 2000; // polling, when the stream fails: while the session works
const IDLE_MS = 8000; // and while it does not
const DRAW_MS = 100; // the page is drawn at most this often
const PAGE = 30;
const PASTED = ".clank/pasted";
const SKIPPED = "{**/node_modules/**,**/.git/**,**/.clank/**,**/__pycache__/**}";
const NOT_RUNNING = "The Clank service does not run: `clank serve --background` starts it.";
const READ_MS = 30_000; // a read of the conversation (or the readout) the service does not answer in this long is given up
const NO_WORKSPACE = "This folder has no Clank workspace: open it with `clank code` first.";

/** What the panel needs of the rest of the extension. */
export interface AgentHost {
  connect(): ClankClient | undefined;
  info(text: string): void;
  warn(text: string): void;
  pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined>;
  openArtifact(made: ArtifactMade): Promise<void>;
  filesColumn(): vscode.ViewColumn;
  /** The fix of what stands in OpenCode's way to the model, pressed on the panel's line. */
  fix(): Promise<void>;
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

/** A wait of `ms`, over sooner when `signal` aborts. */
function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const done = (): void => {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done);
  });
}

/** The panel. */
export class AgentPanel implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private talk: Talk = emptyTalk(); // the live state, from the stream (or the route, when polling)
  private streaming: AbortController | undefined; // the stream open now
  private failures = 0; // stream failures in a row
  private polling = false; // reading the route instead of the stream, after too many failures
  private timer: ReturnType<typeof setTimeout> | undefined; // the next poll
  private drawTimer: ReturnType<typeof setTimeout> | undefined; // the next drawing of the live state
  private reading = false;
  private conversation: Conversation | undefined; // what the page shows, for the actions
  private pinned = ""; // a session the owner picked or started here; else the folder's newest
  private fresh = false; // the next message starts a new session
  private older: PageMessage[] = []; // older messages the owner asked for, before the newest page
  private cursor = ""; // the message to read before, for the next older page ("" when there is none)
  private sent = ""; // what was last sent to the page, so the same is not drawn again
  private shownNotice: { text: string; action: string } | undefined; // what stands in OpenCode's way, under the header

  constructor(
    private readonly extension: vscode.Uri,
    private readonly host: AgentHost,
  ) {}

  dispose(): void {
    clearTimeout(this.timer);
    clearTimeout(this.drawTimer);
    this.stopStream();
    this.panel?.dispose();
  }

  /** What stands in OpenCode's way to the model now, with its fix's words (undefined: nothing): a line under the
   * header until it is gone. */
  notice(notice: { text: string; action: string } | undefined): void {
    this.shownNotice = notice;
    this.drawLive();
  }

  /** The session the panel shows ("" before it has read one), for the readout to follow the same. */
  session(): string {
    return this.conversation?.session?.id ?? "";
  }

  /** Send the agent a message from elsewhere in the window (a board's question, design 0022 §5): to the session the
   * panel shows, or a new one, as a message written in the panel would go; the panel is then shown beside it. */
  async tell(text: string): Promise<void> {
    const client = this.host.connect();
    const folder = this.folder();
    if (!client || !folder) {
      this.host.warn("the Clank service does not run: `clank serve --background` starts it");
      return;
    }
    const found =
      this.conversation ?? (await client.get<Conversation>("agents/conversation", { folder, session: this.pinned, limit: 1 }));
    if (!found.workspace) {
      this.host.warn("this folder has no Clank workspace: open it with `clank code` first");
      return;
    }
    await this.send(client, found.workspace, found.session, text);
    await this.show(false);
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
    this.polling = false; // shown again: the stream is tried again
    this.failures = 0;
    this.follow();
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
        this.follow(); // shown again: the stream resumes from its version
      } else {
        this.stopStream(); // hidden: nothing to draw; the state stays for the resume
        clearTimeout(this.timer);
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
        this.stopStream();
        clearTimeout(this.timer);
        clearTimeout(this.drawTimer);
      }
    });
    return panel;
  }

  // -- the stream

  /** Follow the conversation while the panel shows: the stream, opened again with a growing wait when it breaks
   * (resuming from its version), or the route polled, after too many failures in a row. */
  private follow(): void {
    if (this.polling) {
      void this.tick();
    } else if (!this.streaming) {
      void this.stream();
    }
  }

  /** The session to open another stream on: the one shown, else the pinned one. */
  private shown(): string {
    return this.talk.conversation?.session?.id ?? this.pinned;
  }

  /** Open the stream and apply what it sends until it ends or the panel hides. */
  private async stream(): Promise<void> {
    const control = new AbortController();
    this.streaming = control;
    let wait = RETRY_MS;
    try {
      while (!control.signal.aborted && this.panel?.visible) {
        const client = this.host.connect();
        const folder = this.folder();
        if (!client || !folder) {
          this.draw({ title: "Clank", empty: folder ? NOT_RUNNING : "Open a folder first." });
          await delay(wait, control.signal);
          continue;
        }
        let reopen = false;
        try {
          const parameters = streamParameters(this.talk, folder, this.pinned, PAGE);
          for await (const event of client.stream("agents/conversation/stream", parameters, control.signal)) {
            this.failures = 0;
            wait = RETRY_MS;
            const before = this.talk.conversation?.session?.id;
            this.talk = applyEvent(this.talk, event);
            if (event.name === "snapshot") {
              ({ older: this.older, cursor: this.cursor } = pagesAfterSnapshot(before, this.talk.conversation, this.older, this.cursor));
              void this.refreshReadout(client, folder);
            } else if (event.name === "status" && !(event.data as { busy?: boolean }).busy) {
              void this.refreshReadout(client, folder); // idle again: the foot's numbers once more
            }
            if (this.talk.reconnect !== null) {
              this.forget(); // the folder's newest session changed: the stream is opened on it
              reopen = true;
              break;
            }
            this.scheduleDraw();
            if (event.name === "closing") {
              break; // the service stops: wait, then try again
            }
          }
        } catch {
          if (control.signal.aborted) {
            break;
          }
          this.failures++;
          this.scheduleDraw();
          if (pollsAfter(this.failures)) {
            this.polling = true; // the route, at the old pace, until the panel is shown again
            void this.tick();
            return;
          }
        }
        if (control.signal.aborted) {
          break;
        }
        if (!reopen) {
          await delay(wait, control.signal);
          wait = nextWait(wait);
        }
      }
    } finally {
      if (this.streaming === control) {
        this.streaming = undefined;
      }
    }
  }

  private stopStream(): void {
    this.streaming?.abort();
    this.streaming = undefined;
  }

  /** Another session is to be shown: the live state and the older pages are the old one's. */
  private forget(): void {
    this.talk = { ...emptyTalk(), readout: this.talk.readout };
    this.older = [];
    this.cursor = "";
  }

  /** The model's readout, for the foot and the header, when the stream does not carry it (the session idle). */
  private async refreshReadout(client: ClankClient, folder: string): Promise<void> {
    try {
      const readout = await client.within(READ_MS).get<Readout>("agents/readout", { folder, session: this.shown() });
      this.talk = { ...this.talk, readout };
      this.scheduleDraw();
    } catch {
      // the foot is left as it was; the conversation still shows
    }
  }

  /** Draw the live state soon, at most ten times a second. */
  private scheduleDraw(): void {
    if (this.drawTimer) {
      return;
    }
    this.drawTimer = setTimeout(() => {
      this.drawTimer = undefined;
      this.drawLive();
    }, DRAW_MS);
  }

  /** Draw the live state: the conversation's items (the older pages before the newest), the pending messages, the
   * waits, and the header from the readout. */
  private drawLive(): void {
    const found = this.talk.conversation;
    if (!found) {
      this.draw({ title: "Clank", empty: this.failures ? NOT_RUNNING : "Reading the conversation…" });
      return;
    }
    this.conversation = found;
    if (!found.workspace) {
      this.draw({ title: "Clank", empty: NO_WORKSPACE });
      return;
    }
    const newest = new Set(found.messages.map((each) => each.info.id));
    const messages = [...this.older.filter((each) => !newest.has(each.info.id)), ...found.messages];
    const waiting = waitingItems(found.waiting);
    const busy = Boolean(found.session?.busy);
    const state = waiting.length ? "waiting" : busy ? "working" : found.session ? "idle" : "none";
    const readout = this.talk.readout;
    const foot = readout ? footLine(readout) : null;
    const doing = state === "working" ? foot?.phase || "Working" : state === "waiting" ? "Waits for you" : state === "idle" ? "Idle" : "";
    const link = headerLink(this.polling, this.failures);
    this.draw({
      title: found.session ? found.session.title || "A session" : "A new conversation",
      subtitle: [doing, readout?.slot.title, found.workspace, link].filter(Boolean).join(" · "),
      state, model: readout?.slot.title ?? "", foot, older: Boolean(this.cursor),
      blocks: blocks([...liveItems({ ...this.talk, conversation: { ...found, messages } }), ...waiting]),
      empty: "Write to the agent to start a conversation in this folder.",
    });  // prettier-ignore
  }

  // -- polling, when the stream fails

  /** Read the conversation and the model's readout as one snapshot and draw it; again in a while, while the panel
   * shows and polls. */
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
        this.draw({ title: "Clank", empty: folder ? NOT_RUNNING : "Open a folder first." });
        return;
      }
      const found = await client.within(READ_MS).get<Conversation>("agents/conversation", { folder, session: this.pinned, limit: PAGE });
      const before = this.talk.conversation?.session?.id;
      ({ older: this.older, cursor: this.cursor } = pagesAfterSnapshot(before, found, this.older, this.cursor));
      busy = Boolean(found.session?.busy);
      let readout: Readout | null = this.talk.readout;
      try {
        readout = await client.within(READ_MS).get<Readout>("agents/readout", { folder, session: found.session?.id ?? "" });
      } catch {
        // the foot is left as it was; the conversation still shows
      }
      this.talk = applyEvent({ ...this.talk, readout }, { name: "snapshot", id: undefined, data: found });
      this.drawLive();
    } catch (error) {
      this.draw({ title: "Clank", empty: `The conversation cannot be read: ${error instanceof Error ? error.message : String(error)}` });
    } finally {
      this.reading = false;
      if (this.panel?.visible && this.polling) {
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
      blocks: (shown.blocks ?? []).map(ready), reach: this.shownNotice ?? null,
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
      this.drawLive();
      this.follow();
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
        case "fix":
          await this.host.fix();
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
    if (this.polling && ["send", "act", "permission", "question"].includes(message.type)) {
      setTimeout(() => void this.tick(), 500);
    }
  }

  /** A message to the session (or a new one): shown at once as pending and the composer cleared; given back to the
   * composer when the send fails. */
  private async send(client: ClankClient, workspace: string, session: Conversation["session"], text: string): Promise<void> {
    if (!text.trim()) {
      return;
    }
    if (!workspace) {
      this.host.warn("this folder has no Clank workspace: open it with `clank code` first");
      return;
    }
    const id = `pending-${Date.now()}-${randomBytes(2).toString("hex")}`;
    this.talk = sent(this.talk, id, text);
    this.scheduleDraw();
    void this.panel?.webview.postMessage({ type: "sent" });
    try {
      if (this.fresh || !session) {
        const title = text.split("\n")[0].slice(0, 60);
        const started = await client.post<{ port: number; session: string }>(
          `agents/sessions/${encodeURIComponent(workspace)}/start`, { text, title },
        );  // prettier-ignore
        this.pinned = started.session;
        this.fresh = false;
        this.restream(); // the new session's own stream
      } else {
        await client.post(`agents/sessions/${encodeURIComponent(workspace)}/${session.port}/${encodeURIComponent(session.id)}/message`,
                          { text });  // prettier-ignore
      }
    } catch (error) {
      const [back, talk] = failed(this.talk, id);
      this.talk = talk;
      this.scheduleDraw();
      void this.panel?.webview.postMessage({ type: "insert", text: back });
      throw error;
    }
  }

  /** Follow another session (the one pinned now): the stream is opened on it, the live state the old one's no more. */
  private restream(): void {
    this.forget();
    this.stopStream();
    this.follow();
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
        this.restream();
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
    this.drawLive();
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
