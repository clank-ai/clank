// The agent panel's conversation (design 0021 §4): what `GET /agents/conversation` answers, and the items the panel
// draws from it. A page's messages come in the Monitor's shape (design 0012 §6.1), oldest first; `conversationItems`
// turns them into the owner's messages (OpenCode's synthetic parts left out), the model's text and thinking, each tool
// call with a one-line summary (`callSummary`, Clank's tools named without their server's prefix), a figure the agent
// looked at or showed (inline, as a path in the folder), an artifact it made (a card, §5), a step that failed and a
// compaction. Clank's own message that a job ended is a notice (design 0021 §6), and an owner's comment on an
// artifact that Clank relays is the owner's words (§5). `callView` says what each call did as the panel shows it (an
// icon, a verb, what it was done to); `blocks` folds three calls or more in a row under one line of how many and how
// long. `splitMath` sets math aside before Markdown reads a text, so its underscores stay math; `waitingItems` makes
// what waits in the session into items too. Pure: `agentPanel.ts` asks the route and the webview draws.

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
  time?: { start?: number; end?: number };
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

/** What a call did, as the panel shows it: an icon's name, a verb and what it was done to. */
export interface CallView {
  icon: string;
  verb: string;
  detail: string;
}

export type Item =
  | { kind: "owner"; id: string; text: string; about?: string }
  | { kind: "notice"; id: string; title: string; detail: string; log?: string }
  | { kind: "text"; id: string; text: string }
  | { kind: "thinking"; id: string; text: string }
  | {
      kind: "call";
      id: string;
      tool: string;
      status: string;
      summary: string;
      view: CallView;
      input: string;
      output: string;
      error: string;
      started?: number;
      ended?: number;
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
// Clank's messages to the agent (agents/jobs.py, agents/artifacts.py), read back for what the owner should see
const JOB_ENDED = /^Job (\d+) \((.*?)\) (.+?) after ([^.\n]+)\.(?: The last lines of its log, (\S+?):| Its log, (\S+?), is empty\.)?/;
const JOB_WROTE = /Files written in the folder while it ran, newest first: ([^\n]+?)\.\n/;
const COMMENTED = /^The owner commented on the artifact (.+) \(([\w-]+), version (\d+)\):\n\n([\s\S]*?)\n\nIts files are in /;
// each tool's icon and verb, and the field of its input that says what it was done to
const VIEWS: Record<string, [string, string, string]> = {
  read: ["file", "Read", "filePath"], edit: ["edit", "Edited", "filePath"], multiedit: ["edit", "Edited", "filePath"],
  write: ["edit", "Wrote", "filePath"], patch: ["edit", "Edited", "filePath"], apply_patch: ["edit", "Edited", "filePath"],
  bash: ["terminal", "Ran", "command"], glob: ["search", "Searched", "pattern"], grep: ["search", "Searched", "pattern"],
  list: ["folder", "Listed", "path"], webfetch: ["globe", "Fetched", "url"], websearch: ["globe", "Searched the web", "query"],
  todowrite: ["list", "Updated the plan", ""], todoread: ["list", "Read the plan", ""],
  task: ["agent", "Asked a subagent", "description"], clank_run_job: ["terminal", "Started a job", "command"],
  clank_job_status: ["clock", "Checked on a job", "job"], clank_job_stop: ["stop", "Stopped a job", "job"],
  clank_make_artifact: ["sparkle", "Made an artifact", "name"], clank_look_at_figure: ["image", "Looked at", "path"],
  clank_show_files: ["eye", "Showed you", "files"], clank_find_figures: ["image", "Found figures", ""],
};  // prettier-ignore
const PATHS = new Set(["filePath", "path", "files"]);

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

/** What a call did (module comment): its icon, its verb, and the path, command or name it was given. */
export function callView(tool: string, input: unknown, title: string): CallView {
  const given = givenFields(input);
  const known = VIEWS[tool];
  const [icon, verb, field] = known ?? ["tool", tool.replace(CLANK_TOOL, ""), ""];
  const value = field ? given[field] : GIVEN.map((key) => given[key]).find((each) => typeof each === "string" && each);
  const named = Array.isArray(value) ? value.join(", ") : value === undefined || value === null ? "" : String(value);
  const detail = (named || (known ? "" : title)).split("\n")[0];
  const shown = PATHS.has(field) ? detail.split(", ").map((each) => inFolder(each).replace(/^workspace\//, "")).join(", ") : detail;
  return { icon, verb, detail: shown };
}

/** A message the owner sent, or Clank sent the agent: a job's end as a notice, a relayed comment as the owner's words. */
function userItem(id: string, text: string): Item {
  const job = JOB_ENDED.exec(text);
  if (job) {
    const wrote = JOB_WROTE.exec(text)?.[1];
    const log = job[5] ?? job[6];
    return {
      kind: "notice", id, title: `Job ${job[1]} ended`,
      detail: [job[2], `${job[3]} after ${job[4]}`, ...(wrote ? [`wrote ${wrote}`] : [])].join(" · "),
      ...(log ? { log } : {}),
    };  // prettier-ignore
  }
  const comment = COMMENTED.exec(text);
  if (comment) {
    return { kind: "owner", id, text: comment[4], about: `on ${comment[1]}, version ${comment[3]}` };
  }
  return { kind: "owner", id, text };
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
        items.push(userItem(message.info.id, text));
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
    summary: callSummary(tool, part.input, part.title ?? ""), view: callView(tool, part.input, part.title ?? ""),
    input: inputShown(part.input), output: part.output ?? "", error: part.error ?? "",
    ...(part.time?.start ? { started: part.time.start } : {}), ...(part.time?.end ? { ended: part.time.end } : {}),
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

/** A run of steps (thinking and calls) folded under one line: how many calls, how long, whether one still runs. */
export interface Steps {
  kind: "steps";
  id: string;
  steps: Item[];
  calls: number;
  seconds: number | null;
  running: boolean;
}

export type Block = Item | Steps;

const FOLDED_FROM = 3; // calls in a row folded under one line

/** The items as the panel lays them out: each run of thinking and calls with three calls or more folded under one
 * line (from its first call's start to its last one's end), the other items as they are. */
export function blocks(items: Item[]): Block[] {
  const laid: Block[] = [];
  let run: Item[] = [];
  const close = (): void => {
    const calls = run.filter((each): each is Extract<Item, { kind: "call" }> => each.kind === "call");
    if (calls.length >= FOLDED_FROM) {
      const starts = calls.map((each) => each.started).filter((each): each is number => each !== undefined);
      const ends = calls.map((each) => each.ended ?? each.started).filter((each): each is number => each !== undefined);
      laid.push({
        kind: "steps", id: `${run[0].id}-steps`, steps: run, calls: calls.length,
        seconds: starts.length && ends.length ? Math.round((Math.max(...ends) - Math.min(...starts)) / 1000) : null,
        running: calls.some((each) => each.status === "running" || each.status === "pending"),
      });  // prettier-ignore
    } else {
      laid.push(...run);
    }
    run = [];
  };
  for (const item of items) {
    if (item.kind === "thinking" || item.kind === "call") {
      run.push(item);
    } else {
      close();
      laid.push(item);
    }
  }
  close();
  return laid;
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
