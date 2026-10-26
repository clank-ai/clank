// The agent panel's conversation (design 0021 §4): what `GET /agents/conversation` answers, and the items the panel
// draws from it. A page's messages come in the Monitor's shape (design 0012 §6.1), oldest first; `conversationItems`
// turns them into the owner's messages (OpenCode's synthetic parts left out), the model's text and thinking, each tool
// call with a one-line summary (`callSummary`, Clank's tools named without their server's prefix), a figure the agent
// looked at or showed (inline, as a path in the folder), an artifact it made (a card, §5), a step that failed and a
// compaction. `splitMath` sets math aside before Markdown reads a text, so its underscores stay math; `waitingItems`
// makes what waits in the session into items too. Pure: `agentPanel.ts` asks the route and the webview draws.

/** A message as the page gives it. */
export interface PageMessage {
  info: {
    id: string;
    role: "user" | "assistant";
    agent?: string;
    finish?: string | null;
    error?: string | null;
    summary?: boolean | null;
    created?: number;
  };
  parts: PagePart[];
}

/** A part of a message as the page gives it: by its type, its text, or its call. */
export interface PagePart {
  id: string;
  type: string;
  text?: string;
  length?: number;
  synthetic?: boolean;
  tool?: string;
  status?: string;
  title?: string;
  input?: unknown;
  output?: string;
  error?: string;
}

export interface Permission {
  id: string;
  session: string;
  permission: string;
  patterns: string[];
  metadata: Record<string, unknown>;
}

export interface Question {
  id: string;
  session: string;
  questions: Array<{ question?: string; header?: string; options?: Array<{ label: string; description?: string }> }>;
}

/** What the route answers. */
export interface Conversation {
  folder: string;
  workspace: string | null;
  session: { id: string; title: string; port: number; busy: boolean } | null;
  messages: PageMessage[];
  next: string;
  waiting: { permissions: Permission[]; questions: Question[] };
}

export type Item =
  | { kind: "owner"; id: string; text: string }
  | { kind: "text"; id: string; text: string }
  | { kind: "thinking"; id: string; text: string }
  | {
      kind: "call";
      id: string;
      tool: string;
      status: string;
      summary: string;
      input: string;
      output: string;
      error: string;
    }
  | { kind: "image"; id: string; path: string }
  | { kind: "artifact"; id: string; name: string; title: string; version: number }
  | { kind: "error"; id: string; text: string }
  | { kind: "compaction"; id: string }
  | { kind: "permission"; id: string; permission: string; patterns: string[] }
  | { kind: "question"; id: string; questions: Question["questions"] };

const CLANK_TOOL = /^clank_/;
const IMAGE = /\.(png|jpe?g|gif|webp|svg)$/i;
const CONTAINER = "/workspace/";
// what a call was given, by its tool, when OpenCode gave it no title
const GIVEN = ["command", "filePath", "path", "pattern", "url", "name", "query", "description"];
const MATH = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g;

/** What a call was given, as fields: the page gives it as JSON text, cut past the bridge's limit (then each whole
 * `"key": "text"` before the cut is read). */
export function givenFields(input: unknown): Record<string, unknown> {
  if (input && typeof input === "object") {
    return input as Record<string, unknown>;
  }
  if (typeof input !== "string") {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(input);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    const found: Record<string, unknown> = {};
    for (const match of input.matchAll(/"(\w+)":\s*"((?:[^"\\]|\\.)*)"/g)) {
      try {
        found[match[1]] ??= JSON.parse(`"${match[2]}"`);
      } catch {
        // a text cut inside an escape: left out
      }
    }
    return found;
  }
}

/** A call's input as the panel shows it: laid out when it is whole JSON, else as it came. */
function inputShown(input: unknown): string {
  if (typeof input !== "string") {
    return JSON.stringify(input ?? {}, null, 2);
  }
  try {
    return JSON.stringify(JSON.parse(input), null, 2);
  } catch {
    return input;
  }
}

/** A call in one line: its tool (without Clank's prefix), then its title, else what it was given that says most. */
export function callSummary(tool: string, input: unknown, title: string): string {
  const name = tool.replace(CLANK_TOOL, "");
  const given = givenFields(input);
  const said = title || GIVEN.map((key) => given[key]).find((value) => typeof value === "string" && value) || "";
  return said ? `${name}: ${String(said).split("\n")[0]}` : name;
}

/** The items a page of messages makes (module comment). */
export function conversationItems(messages: PageMessage[]): Item[] {
  const items: Item[] = [];
  for (const message of messages) {
    if (message.info.role === "user") {
      const text = message.parts
        .filter((part) => part.type === "text" && !part.synthetic && part.text)
        .map((part) => part.text)
        .join("\n\n");
      if (text) {
        items.push({ kind: "owner", id: message.info.id, text });
      }
      continue;
    }
    if (message.info.summary) {
      items.push({ kind: "compaction", id: message.info.id });
      continue;
    }
    for (const part of message.parts) {
      items.push(...partItems(part));
    }
    if (message.info.error) {
      items.push({ kind: "error", id: `${message.info.id}-error`, text: message.info.error });
    }
  }
  return items;
}

function partItems(part: PagePart): Item[] {
  if (part.type === "text" && part.text && !part.synthetic) {
    return [{ kind: "text", id: part.id, text: part.text }];
  }
  if (part.type === "reasoning" && part.text?.trim()) {
    return [{ kind: "thinking", id: part.id, text: part.text }];
  }
  if (part.type !== "tool" || !part.tool) {
    return [];
  }
  const tool = part.tool;
  const status = part.status ?? "pending";
  const input = givenFields(part.input);
  const items: Item[] = [{
    kind: "call", id: part.id, tool: tool.replace(CLANK_TOOL, ""), status,
    summary: callSummary(tool, part.input, part.title ?? ""),
    input: inputShown(part.input),
    output: part.output ?? "", error: part.error ?? "",
  }];  // prettier-ignore
  if (status !== "completed") {
    return items;
  }
  const shown = tool === "clank_look_at_figure" ? [input.path] : tool === "clank_show_files" ? asList(input.files) : [];
  for (const [index, path] of shown.entries()) {
    if (typeof path === "string" && IMAGE.test(path)) {
      items.push({ kind: "image", id: `${part.id}-image-${index}`, path: inFolder(path) });
    }
  }
  const made = tool === "clank_make_artifact" ? /version (\d+)/.exec(part.output ?? "") : null;
  if (made && typeof input.name === "string") {
    items.push({
      kind: "artifact", id: `${part.id}-artifact`, name: input.name,
      title: typeof input.title === "string" ? input.title : input.name, version: Number(made[1]),
    });  // prettier-ignore
  }
  return items;
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/** A path as the agent sees it (`/workspace/...`), as a path in the folder. */
function inFolder(path: string): string {
  return path.startsWith(CONTAINER) ? path.slice(CONTAINER.length) : path.replace(/^\.\//, "");
}

/** What waits in the session, as items: each permission with what it asks, then each question. */
export function waitingItems(waiting: Conversation["waiting"]): Item[] {
  return [
    ...waiting.permissions.map((each) => ({
      kind: "permission" as const, id: each.id, permission: each.permission, patterns: each.patterns,
    })),  // prettier-ignore
    ...waiting.questions.map((each) => ({ kind: "question" as const, id: each.id, questions: each.questions })),
  ];
}

/** A text with its math set aside (`@@MATHn@@` in its place), for Markdown to read; then each piece is drawn by KaTeX. */
export function splitMath(text: string): { text: string; math: Array<{ text: string; display: boolean }> } {
  const math: Array<{ text: string; display: boolean }> = [];
  const kept = text.replace(MATH, (_whole, display?: string, bracket?: string, inline?: string, paren?: string) => {
    math.push({ text: display ?? bracket ?? inline ?? paren ?? "", display: display !== undefined || bracket !== undefined });
    return `@@MATH${math.length - 1}@@`;
  });
  return { text: kept, math };
}
