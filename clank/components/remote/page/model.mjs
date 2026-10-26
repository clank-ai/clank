// The phone app's logic that needs no browser (design 0025 §3 and §5): the live stream's state (live, reconnecting with
// the pause's age, offline after thirty seconds with the tries), and what Now draws from the `now` payload (the model's
// line, the machine's gauges, what waits, what works, the summary kept for the offline screen). `app.js` draws from
// these; Node's test runner tests them (`tests/phone/`).

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
