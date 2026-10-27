// The phone app's logic that needs no browser (design 0025 §3, §5, §6 and §7): the live stream's state (live,
// reconnecting with the pause's age, offline after thirty seconds with the tries) and the header's word for it, a
// screen's parts without the absent ones, what Now draws from the `now` payload
// (the model's line, the machine's gauges, what waits, what works, the summary kept for the offline screen), the Flows
// tab's filters, controls and glyphs, and a session's talk built from the conversation stream (the extension's client,
// ported). `app.js` draws from these; Node's test runner tests them (`tests/phone/`).

export const RECONNECT_SECONDS = 5; // how often a dropped stream is tried again
export const OFFLINE_AFTER_SECONDS = 30; // how long a drop may last before the offline screen shows
export const PHASES = {
  "waiting for its slot": "waiting for the model",
  "reading the prompt": "reading",
  answering: "writing",
  "waiting for its engine to start again": "waiting for the engine",
};

// The stream's state from what the link knows: whether it is connected, when it last heard an event, since when it
// fails and how many tries; `nowMs` is the clock. Live while connected; reconnecting while a drop is young, with how long
// the live updates have paused; offline once the drop is `OFFLINE_AFTER_SECONDS` old, with the tries and the next.
export function streamState(link, nowMs) {
  if (link.connected) return { state: "live", pausedSeconds: 0, tries: 0, nextTryIn: 0 };
  const since = link.failedSince ?? nowMs;
  const paused = Math.max(0, Math.floor((nowMs - since) / 1000));
  const nextTryIn = Math.max(0, RECONNECT_SECONDS - (paused % RECONNECT_SECONDS));
  if (paused < OFFLINE_AFTER_SECONDS) return { state: "reconnecting", pausedSeconds: paused, tries: link.tries, nextTryIn };
  return { state: "offline", pausedSeconds: paused, tries: link.tries, nextTryIn };
}

// The header's word for the stream's state, and its class: `link-<state>`, its own. The state's bare name took the looks
// of a session's LIVE tag ("live": a green block in place of the words) and of the offline screen ("offline").
export function linkBadge(link) {
  const words = link.state === "live" ? "● live"
    : link.state === "reconnecting" ? `● reconnecting ${clockText(link.pausedSeconds)}` : "● offline";
  return { kind: `link-${link.state}`, words };
}

// The parts of a screen that are present. The DOM draws a null handed to replaceChildren as the text "null", so an absent
// part (null, undefined, false: the paused line while the stream is live) is left out first (app.js's fill).
export function present(parts) {
  return parts.filter((part) => part !== null && part !== undefined && part !== false);
}

// Seconds as "0:14" or "1:02:03".
export function clockText(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const h = Math.floor(whole / 3600), m = Math.floor((whole % 3600) / 60), s = whole % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? h + ":" : ""}${mm}:${String(s).padStart(2, "0")}`;
}

export function phaseWords(phase) {
  return PHASES[phase] || phase || "";
}

// The model's line at the top of Now: its title and state, its speed, what it does now and the window it uses.
export function modelLine(overview) {
  const model = overview.model || {};
  const agent = overview.agent || {};
  const flying = (agent.requests || [])[0];
  const last = agent.last;
  const line = {
    title: model.title || model.preset || "no model",
    status: model.status || "unknown",
    ready: model.status === "ready",
    doing: "",
    speed: "",
    detail: "",
  };
  if (flying) {
    line.doing = phaseWords(flying.phase) || "working";
    line.speed = flying.per_second ? `${Math.round(flying.per_second)} tok/s` : "";
    const tokens = flying.tokens ? `${Number(flying.tokens).toLocaleString()} tok` : "";
    const seconds = flying.seconds ? `${Math.round(flying.seconds)} s` : "";
    line.detail = [flying.session_title || flying.session || "", tokens, seconds].filter(Boolean).join(" · ");
  } else if (model.status === "ready") {
    line.doing = "idle";
    line.speed = last && last.per_second ? `last ${Math.round(last.per_second)} tok/s` : "";
  } else {
    line.doing = agent.state === "running" ? "" : `gateway ${agent.state || "unknown"}`;
  }
  return line;
}

// The machine as four small gauges: GPU use, its memory, the CPU, the memory; those the machine reports.
export function machineGauges(machine) {
  if (!machine) return [];
  const gauges = [];
  const gpu = machine.gpu;
  if (gpu && gpu.use !== undefined) gauges.push({ label: "GPU", text: `${Math.round(gpu.use)}%`, fraction: gpu.use / 100 });
  if (gpu && gpu.memory_total) {
    gauges.push({ label: "VRAM", text: `${(gpu.memory_used / 1073741824).toFixed(1)} GB`, fraction: gpu.memory_used / gpu.memory_total });
  }
  if (machine.cpu !== undefined && machine.cpu !== null) gauges.push({ label: "CPU", text: `${Math.round(machine.cpu)}%`, fraction: machine.cpu / 100 });
  if (machine.memory_total) {
    gauges.push({ label: "RAM", text: `${Math.round(machine.memory_used / 1073741824)} GB`, fraction: machine.memory_used / machine.memory_total });
  }
  return gauges;
}

// How many things wait for the owner: OpenCode's permissions and questions, the marks, Clank's questions.
export function waitingCount(overview) {
  let count = (overview.questions || []).length + (overview.marks || []).length;
  for (const workspace of overview.workspaces || []) {
    for (const server of workspace.servers || []) count += (server.permissions || []).length + (server.questions || []).length;
  }
  return count;
}

// Every session of every workspace, newest first, each with its workspace and its server's port.
export function allSessions(overview) {
  const found = [];
  for (const workspace of overview.workspaces || []) {
    for (const server of workspace.servers || []) {
      for (const session of server.sessions || []) found.push({ ...session, workspace: workspace.name, port: server.port });
    }
  }
  return found.sort((a, b) => (b.updated || 0) - (a.updated || 0));
}

export function workingRows(overview) {
  return allSessions(overview).filter((session) => session.status === "busy");
}

// The summary the offline screen shows, kept on the phone: names and numbers only, never a file or a message.
export function lastKnown(overview, atMs) {
  const line = modelLine(overview);
  return {
    at: atMs,
    model: `${line.title} · ${line.status}`,
    waiting: waitingCount(overview),
    working: workingRows(overview).map((session) => `${session.workspace} · ${session.title || "a session"}`).slice(0, 3),
  };
}

// The Flows tab (design 0025 §6). The filters keep flows by the state the service's summaries give; a run's controls
// follow its state; each box has a glyph for its state, a gate its own while it waits for you.
export const FILTERS = {
  all: null,
  running: ["running", "paused", "queued", "building"],
  waits: ["waits"],
  ended: ["done", "stopped"],
};
const BOX_GLYPHS = { waiting: "○", running: "●", done: "✓", failed: "✗", stale: "!", skipped: "!", proposed: "?" };

export function flowFilter(rows, which) {
  const states = FILTERS[which];
  return states ? rows.filter((row) => states.includes(row.state)) : rows;
}

export function runControls(run) {
  if (!run || run.status === "done" || run.status === "stopped") return ["run"];
  if (run.status === "queued") return ["stop"];
  return [run.paused ? "resume" : "pause", "stop"];
}

export function boxGlyph(box) {
  if (box.type === "gate" && box.state === "waiting") return "◇";
  return BOX_GLYPHS[box.state] || "○";
}

// A session's talk (design 0025 §7), built from the conversation stream's events (design 0023 §3) as the extension's
// client builds it (`vscode/src/core/talking.ts`, ported here so both read the stream alike). A `snapshot` replaces
// the conversation and its version; `message`, `part`, `delta` and `removed` change one thing each (a delta appends
// to its part's text as the model writes, a part replaces the part whole); `status` says whether the session works;
// `waiting` replaces the waits; `readout` is kept for the header; `session` names the session to open instead. The
// version is the id of the last change applied. A message the owner sends shows at once as pending (`sentTalk`), ends
// when its text arrives as a message of the owner's (the mirror heard OpenCode), and is given back when the send fails
// (`failedTalk`). `talkItems` draws the conversation's items, then the pending ones; `liveIndex` is the item the model
// writes now.
export function emptyTalk() {
  return { conversation: null, version: 0, readout: null, pending: [], reconnect: null };
}

// The state after one event of the stream: its name, its data and its id (the version), when it has one.
export function applyTalk(talk, name, data, id) {
  const given = data || {};
  const version = typeof id === "number" ? id : talk.version;
  switch (name) {
    case "snapshot": {
      const { version: own, ...conversation } = given;
      const next = { ...talk, conversation, version: typeof own === "number" ? own : version };
      return { ...next, pending: settled(next.pending, conversation) };
    }
    case "message":
      return settle(withMessages(talk, version, (messages) => upsert(messages, given.message)));
    case "part":
      return settle(withMessages(talk, version, (messages) => messages.map((each) =>
        (each.info.id === given.message ? { ...each, parts: placed(each.parts, given.part) } : each))));
    case "delta":
      return withMessages(talk, version, (messages) => messages.map((each) => (each.info.id === given.message
        ? { ...each, parts: appended(each.parts, String(given.part), String(given.text ?? "")) } : each)));
    case "removed":
      return withMessages(talk, version, (messages) => (given.part
        ? messages.map((each) => (each.info.id === given.message
          ? { ...each, parts: each.parts.filter((part) => part.id !== given.part) } : each))
        : messages.filter((each) => each.info.id !== given.message)));
    case "status":
      return talk.conversation && talk.conversation.session
        ? { ...talk, version, conversation: { ...talk.conversation, session: { ...talk.conversation.session, busy: Boolean(given.busy) } } }
        : { ...talk, version };
    case "waiting":
      return talk.conversation ? { ...talk, version, conversation: { ...talk.conversation, waiting: given.waiting } } : { ...talk, version };
    case "readout":
      return { ...talk, readout: given.readout || null };
    case "session":
      return { ...talk, reconnect: typeof given.id === "string" ? given.id : "" };
    default:
      return talk;
  }
}

// A message the owner sent, shown at once.
export function sentTalk(talk, id, text) {
  return { ...talk, pending: [...talk.pending, { id, text }] };
}

// A send that failed: its text, to give back to the composer, and the state without it.
export function failedTalk(talk, id) {
  const found = talk.pending.find((each) => each.id === id);
  return [found ? found.text : "", { ...talk, pending: talk.pending.filter((each) => each.id !== id) }];
}

function withMessages(talk, version, change) {
  if (!talk.conversation) return { ...talk, version };
  return { ...talk, version, conversation: { ...talk.conversation, messages: change(talk.conversation.messages) } };
}

function upsert(messages, info) {
  const found = messages.some((each) => each.info.id === info.id);
  const changed = found
    ? messages.map((each) => (each.info.id === info.id ? { ...each, info: { ...each.info, ...info } } : each))
    : [...messages, { info, parts: [] }];
  return changed.sort((a, b) => (a.info.created || 0) - (b.info.created || 0) || a.info.id.localeCompare(b.info.id));
}

function placed(parts, part) {
  return [...parts.filter((each) => each.id !== part.id), part].sort((a, b) => a.id.localeCompare(b.id));
}

function appended(parts, id, text) {
  const found = parts.find((each) => each.id === id);
  if (!found) return placed(parts, { id, type: "text", text, length: text.length });
  const grown = `${found.text || ""}${text}`;
  return parts.map((each) => (each.id === id ? { ...each, text: grown, length: grown.length } : each));
}

// The pending messages still pending: those whose text no message of the owner's carries yet.
function settled(pending, conversation) {
  if (!conversation || !pending.length) return pending;
  const said = new Set(conversation.messages.filter((each) => each.info.role === "user").map((each) =>
    each.parts.filter((part) => part.type === "text" && part.text).map((part) => part.text).join("\n\n")));
  return pending.filter((each) => !said.has(each.text));
}

function settle(talk) {
  return { ...talk, pending: settled(talk.pending, talk.conversation) };
}

// The items a conversation makes, as the phone draws them (design 0021 §4's, the figures and artifacts left to the
// file screen): the owner's words (OpenCode's synthetic parts left out; Clank's word that a job ended as a notice, a
// comment it relayed as the owner's), the model's text, its thinking with its length, each tool call in one line (its
// tool without Clank's prefix, then its title or what it was given that says most) with its state, its result's size
// and its time, a step that failed, a compaction. Each item names its message.
const CLANK_TOOL = /^clank_/;
const GIVEN = ["command", "filePath", "path", "pattern", "url", "name", "query", "description"];
const JOB_ENDED = /^Job (\d+) \((.*?)\) (.+?) after ([^.\n]+)\./;
const COMMENTED = /^The owner commented on the artifact (.+) \(([\w-]+), version (\d+)\):\n\n([\s\S]*?)\n\nIts files are in /;

// What a call was given, as fields: an object as it is, JSON text parsed, text cut past the bridge's limit read for
// each whole `"key": "text"` before the cut.
export function givenFields(input) {
  if (input && typeof input === "object") return input;
  if (typeof input !== "string") return {};
  try {
    const parsed = JSON.parse(input);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    const found = {};
    for (const match of input.matchAll(/"(\w+)":\s*"((?:[^"\\]|\\.)*)"/g)) {
      try { if (!(match[1] in found)) found[match[1]] = JSON.parse(`"${match[2]}"`); } catch { /* cut inside an escape: left out */ }
    }
    return found;
  }
}

// A call in one line: its tool (without Clank's prefix), then its title, else what it was given that says most.
export function callLine(tool, input, title) {
  const name = tool.replace(CLANK_TOOL, "");
  const given = givenFields(input);
  const said = title || GIVEN.map((key) => given[key]).find((value) => typeof value === "string" && value) || "";
  return said ? `${name}: ${String(said).split("\n")[0]}` : name;
}

export function conversationItems(messages) {
  const items = [];
  for (const message of messages) {
    const id = message.info.id;
    if (message.info.role === "user") {
      const text = message.parts.filter((part) => part.type === "text" && !part.synthetic && part.text)
        .map((part) => part.text).join("\n\n");
      if (text) items.push(ownerItem(id, text));
      continue;
    }
    if (message.info.summary) { items.push({ kind: "compaction", id, message: id }); continue; }
    for (const part of message.parts) {
      if (part.type === "text" && part.text && !part.synthetic) {
        items.push({ kind: "text", id: part.id, message: id, text: part.text });
      } else if (part.type === "reasoning" && part.text && part.text.trim()) {
        items.push({ kind: "thinking", id: part.id, message: id, text: part.text, length: part.length || part.text.length });
      } else if (part.type === "tool" && part.tool) {
        const time = part.time || {};
        items.push({
          kind: "call", id: part.id, message: id, tool: part.tool.replace(CLANK_TOOL, ""), status: part.status || "pending",
          line: callLine(part.tool, part.input, part.title || ""), output: part.output || "", error: part.error || "",
          chars: (part.output || "").length, seconds: time.start && time.end ? Math.round((time.end - time.start) / 1000) : null,
        });
      }
    }
    if (message.info.error) items.push({ kind: "error", id: `${id}-error`, message: id, text: message.info.error });
  }
  return items;
}

function ownerItem(id, text) {
  const job = JOB_ENDED.exec(text);
  if (job) return { kind: "notice", id, message: id, title: `Job ${job[1]} ended`, detail: `${job[2]} · ${job[3]} after ${job[4]}` };
  const comment = COMMENTED.exec(text);
  if (comment) return { kind: "owner", id, message: id, text: comment[4], about: `on ${comment[1]}, version ${comment[3]}` };
  return { kind: "owner", id, message: id, text };
}

// The conversation's items, then the pending messages as the owner's.
export function talkItems(talk) {
  const items = talk.conversation ? conversationItems(talk.conversation.messages) : [];
  return [...items, ...talk.pending.map((each) => ({ kind: "owner", id: each.id, message: each.id, text: each.text, pending: true }))];
}

// The item marked LIVE: the last of the model's newest message while the session works; -1 when none.
export function liveIndex(talk, items = talkItems(talk)) {
  const conversation = talk.conversation;
  if (!conversation || !conversation.session || !conversation.session.busy || !conversation.messages.length) return -1;
  const last = conversation.messages[conversation.messages.length - 1];
  if (last.info.role !== "assistant") return -1;
  for (let index = items.length - 1; index >= 0; index -= 1) if (items[index].message === last.info.id) return index;
  return -1;
}
