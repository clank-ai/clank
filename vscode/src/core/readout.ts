// The model's readout (design 0021 §3): what the service's `GET /agents/readout` answers for the window's folder, put
// in words for the status bar (`statusText`) and for the panel under OpenCode's terminal (`panelRows`): the model and
// its speed options; the speed (writing, the last prompt's reading, the drafted tokens accepted, recent steps as a
// graph); what it does now; the context used, part by part (`bar`), the exact window and what is retrieved; whether
// the engine holds this session's conversation; the GPU; the jobs running in the folder's workspace (design 0021 §6).
// Pure: `extension.ts` asks the service and draws.

/** One recent figure set of the session's, as `now` gives it (design 0012 §5). */
export interface ReadoutNow {
  state: string;
  phase: string;
  working: boolean;
  seconds: number | null;
  call: { tool: string; title: string; input: string } | null;
  writing: { tool: string; arguments: string } | null;
  prompt: { first_ms: number | null; reading: boolean; tokens: number | null; cached: number | null; of: string };
  speed: { now: number | null; steps: number[] };
}

/** The session's context totals, as the service gives them (design 0012 §4). */
export interface ReadoutContext {
  window: number | null;
  line: number | null;
  used: number | null;
  cache_share: number | null;
  gpu: { device: string; exact: number | null; stored: number | null; attended: number | null; elsewhere: number | null } | null;
  holder: { this: boolean; subagent: boolean; taken: boolean; lost: boolean | string } | null;
  parts: { tokens: number; parts: Array<{ part: string; label: string; tokens: number; share: number }> } | null;
}

/** The service's readout of a folder. */
export interface Readout {
  folder: string;
  workspace: string | null;
  session: { id: string; title: string } | null;
  now: ReadoutNow | null;
  context: ReadoutContext | null;
  slot: { status: string; preset: string | null; title: string; speed_options: Record<string, unknown> };
  gpu: { name: string; use: number | null; memory_used: number | null; memory_total: number | null } | null;
  drafts: { tokens: number; drafted: number; accepted: number; share: number | null } | null;
  jobs?: Array<{ job: number; title: string; state: string; seconds: number }>; // absent from a service before jobs
}

/** One part of the context bar: its label, its tokens, and its share of the window. */
export interface Segment {
  label: string;
  tokens: number;
  share: number;
}

/** The panel's rows, in words. */
export interface PanelRows {
  title: string;
  speed: string;
  graph: string;
  now: string;
  context: string;
  bar: Segment[];
  exact: string;
  engine: string;
  machine: string;
  jobs: string;
}

const BARS = "▁▂▃▄▅▆▇█";
const READ_SPEED_FROM = 2000; // new tokens of a prompt: fewer, and the time to its first token is mostly waiting
const WRITING = new Set(["thinking", "answering", "writing"]);
const GB = 2 ** 30;

/** A count of tokens as people read it: 161K, 1.5K, 950. */
export function tokens(count: number | null | undefined): string {
  if (count === null || count === undefined) {
    return "?";
  }
  if (count >= 10_000) {
    return `${Math.round(count / 1000)}K`;
  }
  return count >= 1000 ? `${(count / 1000).toFixed(1)}K` : String(count);
}

/** The newest `width` values as bars between the lowest and the highest; a level line when they are alike. */
export function sparkline(values: number[], width = 24): string {
  const shown = values.slice(-width);
  if (!shown.length) {
    return "";
  }
  const low = Math.min(...shown);
  const high = Math.max(...shown);
  return shown
    .map((value) => (high === low ? BARS[3] : BARS[Math.floor(((value - low) / (high - low)) * (BARS.length - 1))]))
    .join("");
}

/** The status bar's line: the speed, the context used of the window and the phase; the model with no session. */
export function statusText(readout: Readout | undefined): string {
  if (readout === undefined) {
    return "$(pulse) Clank: no readout";
  }
  const { now, context, slot } = readout;
  if (now === null) {
    return `$(pulse) ${slot.title} · ${slot.status}`;
  }
  const speed = now.speed.now ? `${WRITING.has(now.state) ? "" : "last "}${Math.round(now.speed.now)} tok/s` : "";
  const used = context?.used && context.window ? `${tokens(context.used)}/${tokens(context.window)}` : "";
  return `$(pulse) ${[speed, used, now.phase].filter(Boolean).join(" · ")}`;
}

/** The agent panel's foot (design 0021 §4): the speed, the context used of the window (and its share), the drafted
 * tokens accepted, the GPU's memory, the model, and what it does now; a figure not read is left empty. */
export interface FootLine {
  speed: string;
  used: string;
  window: string;
  share: number;
  drafts: string;
  gpu: string;
  model: string;
  phase: string;
}

export function footLine(readout: Readout): FootLine {
  const { now, context, gpu, drafts, slot } = readout;
  const speed = now?.speed.now ? `${WRITING.has(now.state) ? "" : "last "}${Math.round(now.speed.now)} tok/s` : "";
  const phase = now?.phase ?? "";
  return {
    speed,
    used: context?.used ? tokens(context.used) : "",
    window: context?.window ? tokens(context.window) : "",
    share: context?.used && context.window ? context.used / context.window : 0,
    drafts: drafts?.share === null || drafts?.share === undefined ? "" : `drafts ${Math.round(drafts.share * 100)} %`,
    gpu: gpu?.memory_used && gpu.memory_total
      ? `GPU ${(gpu.memory_used / GB).toFixed(1)} / ${(gpu.memory_total / GB).toFixed(1)} GB`
      : "",
    model: slot.title,
    phase: phase ? phase[0].toUpperCase() + phase.slice(1) : "",
  };
}

/** The panel's rows (module comment). */
export function panelRows(readout: Readout): PanelRows {
  const { now, context, slot, gpu } = readout;
  return {
    title: [slot.title, slot.status, ...speedOptions(slot.speed_options)].join(" · "),
    speed: speedRow(readout),
    graph: sparkline(now?.speed.steps ?? []),
    now: now ? nowRow(now) : "",
    context: contextRow(context),
    bar: context ? bar(context) : [],
    exact: exactRow(context),
    engine: engineRow(context),
    machine: gpu?.memory_used && gpu.memory_total
      ? `GPU ${(gpu.memory_used / GB).toFixed(1)} of ${(gpu.memory_total / GB).toFixed(1)} GB` +
        (gpu.use === null ? "" : ` · ${Math.round(gpu.use)}% busy`)
      : "the GPU's meters are not read",
    jobs: jobsRow(readout.jobs ?? []),
  };
}

function jobsRow(jobs: NonNullable<Readout["jobs"]>): string {
  if (!jobs.length) {
    return "";
  }
  const each = jobs.map(
    (job) => `${job.job} ${job.title} (${job.state === "running" ? `${Math.floor(job.seconds / 60)} min` : job.state})`,
  );
  return `jobs: ${each.join(" · ")}`;
}

function speedOptions(options: Record<string, unknown>): string[] {
  const said: string[] = [];
  if (typeof options["spec.draft_tokens"] === "number") {
    said.push(`${options["spec.draft_tokens"]} drafted tokens a step`);
  }
  if (typeof options.cuda_graphs === "boolean") {
    said.push(`CUDA graphs ${options.cuda_graphs ? "on" : "off"}`);
  }
  return said;
}

function speedRow({ now, drafts }: Readout): string {
  if (now === null) {
    return "no session of this folder yet";
  }
  const said: string[] = [];
  if (now.speed.now) {
    said.push(`${WRITING.has(now.state) ? "writing" : "last step"} ${Math.round(now.speed.now)} tok/s`);
  }
  const { prompt } = now;
  if (prompt.of === "the last step" && !prompt.reading && prompt.first_ms && prompt.tokens) {
    const fresh = Math.max(prompt.tokens - (prompt.cached ?? 0), 0);
    const seconds = prompt.first_ms / 1000;
    said.push(
      fresh >= READ_SPEED_FROM
        ? `read ${Math.round(fresh / seconds).toLocaleString("en-US")} tok/s`
        : `read ${fresh.toLocaleString("en-US")} new tokens in ${seconds.toFixed(1)} s`, // too few for a speed
    );
  }
  if (drafts?.share !== null && drafts?.share !== undefined) {
    said.push(`drafts ${Math.round(drafts.share * 100)}% accepted`);
  }
  return said.join(" · ") || "no step has ended yet";
}

function nowRow(now: ReadoutNow): string {
  const what = now.call?.tool && now.state === "tool"
    ? `${now.phase}: ${now.call.tool}`
    : now.writing?.tool && now.state === "writing"
      ? `${now.phase}: ${now.writing.tool}`
      : now.phase;
  return now.seconds === null || !now.working ? what : `${what} · ${Math.round(now.seconds)} s`;
}

function contextRow(context: ReadoutContext | null): string {
  if (context === null || !context.used || !context.window) {
    return "the context shows once the agent has answered";
  }
  const said = [`${tokens(context.used)} of ${tokens(context.window)} used (${Math.round((context.used / context.window) * 100)}%)`];
  if (context.line) {
    said.push(`compaction at ${tokens(context.line)}`);
  }
  if (context.cache_share !== null) {
    said.push(`${Math.round(context.cache_share * 100)}% read from the cache`);
  }
  return said.join(" · ");
}

function bar(context: ReadoutContext): Segment[] {
  const window = context.window ?? 0;
  if (!window || !context.parts) {
    return [];
  }
  const parts = [...context.parts.parts]
    .filter((part) => part.tokens > 0)
    .sort((a, b) => b.tokens - a.tokens)
    .map((part) => ({ label: part.label, tokens: part.tokens, share: part.tokens / window }));
  const free = Math.max(window - (context.used ?? context.parts.tokens), 0);
  return [...parts, { label: "free", tokens: free, share: free / window }];
}

function exactRow(context: ReadoutContext | null): string {
  const gpu = context?.gpu;
  if (!gpu || gpu.attended === null) {
    return "";
  }
  const where = gpu.device === "cloud" ? "in the cloud" : gpu.device === "cpu" ? "in system memory" : "on the GPU";
  return gpu.elsewhere
    ? `${tokens(gpu.attended)} attended exactly ${where}; ${tokens(gpu.elsewhere)} retrieved from system memory`
    : `all of it attended exactly ${where}`;
}

function engineRow(context: ReadoutContext | null): string {
  const holder = context?.holder;
  if (!holder) {
    return "";
  }
  if (holder.this) {
    return "the engine holds this session's conversation";
  }
  if (holder.subagent) {
    return "the engine holds its subagent's conversation";
  }
  const again = `this session's next step reads its ${tokens(context?.used)} again`;
  return holder.taken ? `the engine holds another conversation: ${again}` : `the engine holds no conversation: ${again}`;
}
