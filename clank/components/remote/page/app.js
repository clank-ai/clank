// Clank's phone page (design 0005 §1, §4): pair, see what the model and the agents do now, reply to what waits, drive
// a session, start a task, see the files sent. It looks like the console: monospace, thin rules, rows to tap.
// Four tabs: now (what matters first), work (every workspace and its sessions), files, and log: everything this phone
// and the computer exchanged, each exchange whole. Everything comes from this page's own address; every action carries
// the X-Clank-Phone header.
"use strict";

const view = document.getElementById("view");
const title = document.getElementById("title");
const back = document.getElementById("back");
const status = document.getElementById("status");
const tabs = document.getElementById("tabs");
const toast = document.getElementById("toast");
const waitingCount = document.getElementById("count-now");
const NOW_SECONDS = 4;
const BUSY_SECONDS = 2;
const IDLE_SECONDS = 8;
const RECENT = 5;
const LOG_LIMIT = 100;
const PHASES = { "waiting for its slot": "waiting for the model", "reading the prompt": "reading", "answering": "writing",
  "waiting for its engine to start again": "waiting for the engine" };

// tab: now, work or files; place: a workspace's page or a session's, over the tab; overview: the last one read; notes: a
// flow's note being written, by its question; reads: the files of a flow's question read here.
const state = { tab: "now", place: null, overview: null, messages: [], timer: null, task: "", log: { items: [], open: {} }, notes: {}, reads: {} };

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function say(text, ok = false) {
  toast.textContent = text;
  toast.className = ok ? "toast ok" : "toast";
  clearTimeout(say.timer);
  say.timer = setTimeout(() => toast.classList.add("hidden"), 4000);
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Clank-Phone": "1" }, body: JSON.stringify(body),
  };
  const answer = await fetch(path, { credentials: "same-origin", ...options });
  let found = null;
  try { found = await answer.json(); } catch (error) { found = null; }
  if (!answer.ok) {
    const error = new Error((found && found.error) || `the computer answered ${answer.status}`);
    error.status = answer.status;
    throw error;
  }
  return found;
}

function ago(when) {
  if (!when) return "";
  const millis = typeof when === "number" ? (when > 1e12 ? when : when * 1000) : Date.parse(when);
  const seconds = Math.max(0, (Date.now() - millis) / 1000);
  if (seconds < 60) return "now";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

function gb(bytes) { return (bytes / 1073741824).toFixed(1); }

function size(bytes) { return bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`; }

function clock(when) { return new Date(when).toLocaleTimeString([], { hour12: false }); }

// A gauge as the console draws one: a bar of blocks, the filled part in its tone, the rest dark.
function gauge(fraction, width = 10) {
  const filled = Math.max(0, Math.min(width, Math.round(fraction * width)));
  return el("span", { class: "gauge" }, el("span", { class: tone(fraction) }, "█".repeat(filled)),
    el("span", { class: "rest" }, "█".repeat(width - filled)));
}

function tone(fraction) { return fraction > 0.9 ? "bad" : fraction > 0.7 ? "warn" : "good"; }

// A message's text, kept as text: code blocks, inline code and bold; nothing from it becomes markup.
function rich(text) {
  const box = el("div");
  const pieces = text.split(/```[a-zA-Z0-9_-]*\n?/);
  pieces.forEach((piece, index) => {
    if (index % 2 === 1) { box.append(el("pre", {}, piece.replace(/\n$/, ""))); return; }
    for (const paragraph of piece.split(/\n{2,}/)) {
      if (!paragraph.trim()) continue;
      const line = el("p");
      for (const part of paragraph.split(/(`[^`]+`|\*\*[^*]+\*\*)/)) {
        if (part.startsWith("`") && part.endsWith("`") && part.length > 1) line.append(el("code", {}, part.slice(1, -1)));
        else if (part.startsWith("**") && part.endsWith("**") && part.length > 3) line.append(el("strong", {}, part.slice(2, -2)));
        else part.split("\n").forEach((text, number) => { if (number) line.append(el("br")); line.append(text); });
      }
      box.append(line);
    }
  });
  return box;
}

function section(name, count) {
  return el("div", { class: "sect" }, name, count ? el("span", { class: "n" }, `(${count})`) : null);
}

function kv(rows) {
  return el("div", { class: "kv" }, rows.flatMap(([key, value]) => [el("span", { class: "k" }, key), el("span", { class: "v" }, value)]));
}

function row({ glyph, glyphClass = "dim", line, sub, meta, onclick }) {
  return el("div", { class: "row", onclick },
    el("span", { class: "glyph " + glyphClass }, glyph),
    el("div", { class: "main" }, el("div", { class: "line" }, line), sub ? el("div", { class: "sub" }, sub) : null),
    meta ? el("span", { class: "meta" }, meta) : null,
    onclick ? el("span", { class: "go" }, "›") : null);
}

// Every session of every running workspace, newest first, each with its workspace and its server's port.
function allSessions(overview) {
  const found = [];
  for (const workspace of overview.workspaces) {
    for (const server of workspace.servers) {
      for (const session of server.sessions) found.push({ ...session, workspace: workspace.name, port: server.port });
    }
  }
  return found.sort((a, b) => (b.updated || 0) - (a.updated || 0));
}

function sessionRow(session) {
  const busy = session.status === "busy";
  return row({
    glyph: busy ? "●" : "○", glyphClass: busy ? "good" : "dim", line: session.title || "a session",
    sub: `${session.workspace} · ${busy ? "working" : "idle"}`, meta: ago(session.updated),
    onclick: () => openSession(session.workspace, session.port, session.id, session.title),
  });
}

// The status lines: the model, what it does now, the GPU, the CPU and memory.
function statusLines(overview) {
  const model = overview.model;
  const ready = model.status === "ready";
  const rows = [["model", el("span", {}, el("span", { class: ready ? "good" : model.status === "starting" ? "warn" : "bad" }, model.status),
    model.title ? ` · ${model.title}` : "")]];
  const agent = overview.agent || {};
  const flying = (agent.requests || [])[0];
  if (flying) {
    const speed = flying.per_second ? ` · ${flying.per_second} tok/s` : "";
    rows.push(["now", el("span", {}, el("span", { class: "acc" }, PHASES[flying.phase] || flying.phase),
      ` · ${flying.tokens.toLocaleString()} tok${speed} · ${Math.round(flying.seconds)}s`)]);
  } else if (agent.last) {
    const last = agent.last;
    const speed = last.per_second ? ` at ${last.per_second} tok/s` : "";
    rows.push(["now", el("span", { class: "muted" }, `idle · last ${last.tokens.toLocaleString()} tok${speed}, ${ago(last.time)} ago`)]);
  } else {
    rows.push(["now", el("span", { class: "muted" }, agent.state === "running" ? "idle" : `gateway ${agent.state || "unknown"}`)]);
  }
  const machine = overview.machine;
  if (machine && machine.gpu) {
    const gpu = machine.gpu;
    rows.push(["gpu", el("span", {}, gauge(gpu.use / 100),
      ` ${Math.round(gpu.use)}% · ${gb(gpu.memory_used)}/${gb(gpu.memory_total)} GB · ${gpu.temperature}°C`)]);
  }
  if (machine && machine.memory_total) {
    rows.push(["cpu", el("span", {}, gauge(machine.cpu / 100),
      ` ${Math.round(machine.cpu)}% · mem ${gb(machine.memory_used)}/${gb(machine.memory_total)} GB`)]);
  }
  return kv(rows);
}

// A question a flow waits for (design 0013 §10): under its flow, the box it waits at, the files it shows (each read
// here as it stands in the folder, what an approval takes), what each answer does, and a note for the answers that take
// words (send back's, try again's). The note is kept while the page redraws, until the question is answered.
const WAITS = { you: "your part", gate: "gate", failed: "a box failed", done: "a box is done" };

function flowBox(question) {
  const flow = question.flow;
  const notes = flow.notes || {};
  const noted = Object.keys(notes);
  const read = async (index) => {
    const key = `${question.id}/${index}`;
    if (state.reads[key]) { delete state.reads[key]; draw(); return; }
    try { state.reads[key] = await api(`api/flow-files/${encodeURIComponent(question.id)}/${index}`); draw(); }
    catch (error) { say(error.message); }
  };
  const files = (flow.files || []).map((file, index) => {
    const shown = state.reads[`${question.id}/${index}`];
    const tries = file.tries.length ? ` · ${file.tries.length} ${file.tries.length === 1 ? "try" : "tries"} kept` : "";
    const text = shown && (typeof shown.text === "string" ? el("pre", {}, shown.text) : el("div", { class: "dim" }, shown.why));
    return el("div", {},
      el("div", { class: "btns" },
        el("span", {}, file.path, el("span", { class: "dim" }, file.box ? ` · from ${file.box}${tries}` : "")),
        el("button", { class: "btn small", onclick: () => read(index) }, shown ? "hide" : "read")),
      text || null);
  });
  let note = null;
  if (noted.length) {
    note = el("textarea", { placeholder: noted.map((id) => notes[id]).join(" ") });
    note.value = state.notes[question.id] || "";
    note.addEventListener("input", () => { state.notes[question.id] = note.value; });
  }
  const where = flow.box_title ? ` · ${WAITS[flow.kind] || "waits"} · ${flow.box_title}` : "";
  const effects = question.options.filter((option) => option.effect).map((option) => `${option.label}: ${option.effect}`);
  return el("div", { class: "box waiting" },
    el("div", { class: "head" }, `flow · ${flow.title}${where}`),
    el("div", {}, question.title),
    question.detail ? el("pre", {}, question.detail) : null,
    files, note,
    effects.length ? el("div", { class: "dim" }, effects.join(" · ")) : null,
    el("div", { class: "btns" }, question.options.map((option) => el("button", {
      class: "btn small", onclick: async () => {
        const words = notes[option.id] ? (state.notes[question.id] || "").trim() : "";
        try {
          await api(`api/clank-questions/${question.id}`, { option: option.id, ...(words ? { text: words } : {}) });
          delete state.notes[question.id];
          say("answered", true);
          refresh();
        } catch (error) { say(error.message); }
      },
    }, option.label))));
}

// A mark of the Monitor's Watch for told to the phone (design 0012 §8): its rule, its session, why, what its rule could
// not do and why, and "seen", which takes it off this list.
function markBox(mark) {
  const waited = (mark.did || []).filter((each) => !each.done).map((each) => `${each.action}: ${each.why}`);
  return el("div", { class: "box waiting" },
    el("div", { class: "head" }, `${mark.workspace} · watch for · ${mark.name}`),
    el("div", { class: "dim" }, `${mark.title || mark.session} · ${ago(mark.time)}`),
    el("div", {}, mark.why),
    waited.length ? el("div", { class: "dim" }, waited.join("; ")) : null,
    el("div", { class: "btns" }, el("button", {
      class: "btn small", onclick: async () => {
        try { await api("api/marks/seen", { ids: [mark.id] }); say("seen", true); refresh(); }
        catch (error) { say(error.message); }
      },
    }, "seen")));
}

// What waits: OpenCode's permissions and questions (in one workspace, or in all), the Monitor's marks told to the phone,
// and Clank's own questions.
function waitingBoxes(overview, only = null) {
  const boxes = [];
  for (const workspace of overview.workspaces) {
    if (only && workspace.name !== only) continue;
    for (const server of workspace.servers) {
      for (const asked of server.permissions) {
        const diff = asked.metadata && (asked.metadata.diff || asked.metadata.command);
        const reply = (answer) => async () => {
          try { await api(`api/permissions/${encodeURIComponent(workspace.name)}/${server.port}/${asked.id}`, { reply: answer }); say("replied", true); refresh(); }
          catch (error) { say(error.message); }
        };
        boxes.push(el("div", { class: "box waiting" },
          el("div", { class: "head" }, `${workspace.name} · asks to ${asked.permission}`),
          (asked.patterns || []).length ? el("div", { class: "dim" }, asked.patterns.join(", ")) : null,
          diff ? el("pre", {}, diff) : null,
          el("div", { class: "btns" },
            el("button", { class: "btn ok", onclick: reply("once") }, "allow once"),
            el("button", { class: "btn", onclick: reply("always") }, "always"),
            el("button", { class: "btn no", onclick: reply("reject") }, "reject"))));
      }
      for (const asked of server.questions) {
        const answers = asked.questions.map(() => []);
        const send = async () => {
          try { await api(`api/questions/${encodeURIComponent(workspace.name)}/${server.port}/${asked.id}`, { answers }); say("answered", true); refresh(); }
          catch (error) { say(error.message); }
        };
        const blocks = asked.questions.map((question, index) => el("div", {},
          el("div", {}, question.question),
          el("div", { class: "btns" }, (question.options || []).map((option) =>
            el("button", { class: "btn small", onclick: () => { answers[index] = [option.label]; send(); } }, option.label))),
          question.custom === false ? null : el("input", { placeholder: "or your own answer",
            oninput: (event) => { answers[index] = event.target.value ? [event.target.value] : []; } })));
        boxes.push(el("div", { class: "box waiting" }, el("div", { class: "head" }, `${workspace.name} · asks`), blocks,
          el("div", { class: "btns" }, el("button", { class: "btn go", onclick: send }, "send the answer"))));
      }
    }
  }
  for (const mark of (overview.marks || []).filter((each) => !only || each.workspace === only)) boxes.push(markBox(mark));
  for (const question of only ? [] : overview.questions) {
    if (question.flow) {
      boxes.push(flowBox(question));
      continue;
    }
    boxes.push(el("div", { class: "box waiting" },
      el("div", { class: "head" }, `clank · ${question.title}`), question.detail ? el("pre", {}, question.detail) : null,
      el("div", { class: "btns" }, question.options.map((option) => el("button", {
        class: "btn small", onclick: async () => {
          try { await api(`api/clank-questions/${question.id}`, { option: option.id }); say("answered", true); refresh(); }
          catch (error) { say(error.message); }
        },
      }, option.label)))));
  }
  return boxes;
}

// A file as a row: a small picture of it, its caption, its workspace and when.
function fileRow(file) {
  const href = `api/files/${encodeURIComponent(file.workspace)}/${encodeURIComponent(file.file)}`;
  const image = (file.mime || "").startsWith("image/");
  return el("a", { class: "row", href, target: "_blank", rel: "noopener" },
    image ? el("img", { class: "thumb", src: href, alt: "", loading: "lazy" }) : el("span", { class: "thumb doc" }, "[f]"),
    el("div", { class: "main" }, el("div", { class: "line" }, file.caption || file.from || file.file),
      el("div", { class: "sub" }, `${file.workspace} · ${ago(file.sent)}`)),
    el("span", { class: "go" }, "›"));
}

function fileTile(file) {
  const href = `api/files/${encodeURIComponent(file.workspace)}/${encodeURIComponent(file.file)}`;
  const image = (file.mime || "").startsWith("image/");
  return el("a", { class: "file", href, target: "_blank", rel: "noopener" },
    image ? el("img", { src: href, alt: file.caption || file.file, loading: "lazy" }) : el("div", { class: "doc" }, "[file]"),
    el("div", { class: "cap" }, file.caption || file.from || file.file, el("div", { class: "dim" }, `${file.workspace} · ${ago(file.sent)}`)));
}

// A new task for a running workspace's agent: which workspace (when more than one runs), what to do, start.
function taskBox(workspaces) {
  const running = workspaces.filter((workspace) => workspace.state === "running" && !workspace.problem);
  if (!running.length) return el("div", { class: "empty" }, "No workspace runs: open one on the computer to start a task.");
  const choice = running.length > 1 ? el("select", {}, running.map((workspace) => el("option", { value: workspace.name }, workspace.name))) : null;
  const text = el("textarea", { placeholder: `e.g. "send me the figure of …"` });
  text.value = state.task;
  text.addEventListener("input", () => { state.task = text.value; });
  return el("div", { class: "task" }, choice, text, el("div", { class: "btns" }, el("button", {
    class: "btn go", onclick: async () => {
      if (!text.value.trim()) return;
      const workspace = choice ? choice.value : running[0].name;
      try {
        const started = await api(`api/sessions/${encodeURIComponent(workspace)}/start`, { text: text.value });
        state.task = "";
        say("started", true);
        openSession(workspace, started.port, started.session, "From the phone");
      } catch (error) { say(error.message); }
    },
  }, running.length > 1 ? "start" : `start in ${running[0].name}`)));
}

function nowView(overview) {
  const parts = [section("status"), statusLines(overview)];
  const waiting = waitingBoxes(overview);
  if (waiting.length) parts.push(section("waiting for you", waiting.length), ...waiting);
  const sessions = allSessions(overview);
  const busy = sessions.filter((session) => session.status === "busy");
  if (busy.length) parts.push(section("working now"), ...busy.map(sessionRow));
  const idle = sessions.filter((session) => session.status !== "busy").slice(0, RECENT);
  parts.push(section("recent"), ...(idle.length ? idle.map(sessionRow) : [el("div", { class: "empty" }, "No session yet.")]));
  const problems = overview.workspaces.filter((workspace) => workspace.problem);
  for (const workspace of problems) parts.push(el("div", { class: "box" }, el("span", { class: "warn" }, `${workspace.name}: `), workspace.problem));
  parts.push(section("new task"), taskBox(overview.workspaces));
  if (overview.files.length) parts.push(section("last files"), ...overview.files.slice(0, 2).map(fileRow));
  return parts;
}

function workView(overview) {
  const parts = [section("workspaces")];
  if (!overview.workspaces.length) parts.push(el("div", { class: "empty" }, "No workspace yet: open a folder in Clank on the computer."));
  for (const workspace of overview.workspaces) {
    const running = workspace.state === "running";
    const sessions = workspace.servers.reduce((sum, server) => sum + server.sessions.length, 0);
    const busy = workspace.servers.some((server) => server.sessions.some((session) => session.status === "busy"));
    parts.push(row({
      glyph: running ? "●" : "○", glyphClass: workspace.problem ? "warn" : running ? "good" : "dim", line: workspace.name,
      sub: workspace.problem ? "its agents cannot be reached" : running ? `${sessions} session${sessions === 1 ? "" : "s"}${busy ? " · working" : ""}` : workspace.state,
      onclick: () => openWorkspace(workspace.name),
    }));
  }
  return parts;
}

function workspaceView(overview) {
  const workspace = overview.workspaces.find((each) => each.name === state.place.workspace);
  if (!workspace) return [el("div", { class: "empty" }, "This workspace is gone.")];
  const parts = [kv([["state", el("span", { class: workspace.state === "running" ? "good" : "dim" }, workspace.state)]])];
  if (workspace.problem) parts.push(el("div", { class: "box" }, el("span", { class: "warn" }, "! "), workspace.problem));
  const waiting = waitingBoxes(overview, workspace.name);
  if (waiting.length) parts.push(section("waiting for you", waiting.length), ...waiting);
  const sessions = allSessions({ ...overview, workspaces: [workspace] });
  parts.push(section("sessions"), ...(sessions.length ? sessions.map(sessionRow) : [el("div", { class: "empty" }, "No session yet.")]));
  if (workspace.state === "running" && !workspace.problem) parts.push(section("new task"), taskBox([workspace]));
  return parts;
}

function filesView(overview) {
  if (!overview.files.length) return [el("div", { class: "empty" }, "Nothing sent yet. Ask an agent to send you a figure.")];
  return [section("sent to you", overview.files.length), el("div", { class: "files" }, overview.files.map(fileTile))];
}

// The log: what this phone asked and what it was sent, newest first; an exchange opens whole when tapped. It is read
// when the tab opens and when asked (reading it is an exchange too).
async function loadLog() {
  try { state.log.items = (await api(`api/traffic?limit=${LOG_LIMIT}`)).exchanges; draw(); }
  catch (error) { say(error.message); }
}

async function toggleExchange(id) {
  if (state.log.open[id]) { delete state.log.open[id]; draw(); return; }
  try { state.log.open[id] = await api(`api/traffic/${id}`); draw(); }
  catch (error) { say(error.message); }
}

function bodyText(value) {
  if (value === null || value === undefined) return "(nothing)";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function logView() {
  const parts = [section("this phone and the computer", state.log.items.length),
    el("div", { class: "dim" }, "Everything this phone asked and was sent, newest first. Tap one to see it whole."),
    el("div", { class: "btns" }, el("button", { class: "btn small", onclick: loadLog }, "read again"))];
  for (const item of state.log.items) {
    const ok = item.status < 300;
    parts.push(row({
      glyph: ok ? "·" : "!", glyphClass: ok ? "dim" : "warn", line: `${item.method} ${item.path}`,
      sub: `${clock(item.time)} · ${item.status} · ${size(item.bytes_out)} · ${Math.round(item.ms)} ms${item.same_as ? " · same as before" : ""}`,
      onclick: () => toggleExchange(item.id),
    }));
    const open = state.log.open[item.id];
    if (open) {
      parts.push(el("div", { class: "box" },
        el("div", { class: "dim" }, `sent by this phone (${size(open.bytes_in)})`), el("pre", {}, bodyText(open.request)),
        el("div", { class: "dim" }, `sent to this phone (${size(open.bytes_out)}, ${open.response_type || "no type"})`),
        el("pre", {}, bodyText(open.response))));
    }
  }
  if (!state.log.items.length) parts.push(el("div", { class: "empty" }, "Nothing yet."));
  return parts;
}

function messageView(message) {
  const parts = [];
  for (const part of message.parts) {
    if (part.type === "text" && part.text.trim()) parts.push(rich(part.text));
    else if (part.type === "tool") {
      const mark = part.status === "completed" ? "✓" : part.status === "error" ? "✗" : "…";
      const kind = part.status === "error" ? " error" : part.status === "completed" ? " done" : "";
      parts.push(el("div", { class: "tool" + kind }, `${mark} ${part.tool}${part.title ? "  " + part.title : ""}`));
    } else if (part.type === "reasoning" && part.length) {
      parts.push(el("div", { class: "tool" }, `· thought it over (${part.length.toLocaleString()} characters)`));
    }
  }
  if (message.error) parts.push(el("div", { class: "tool error" }, `✗ ${message.error}`));
  if (!parts.length) return null;
  const you = message.role === "user";
  return el("div", { class: "msg" }, el("div", { class: "who " + (you ? "you" : "agent") }, you ? "› you" : "◆ agent"), parts);
}

// A session's page keeps its composer from the moment it opens: the polls redraw the conversation above it, never the
// box being typed in (a phone's keyboard would close).
function sessionParts(place) {
  const where = `api/sessions/${encodeURIComponent(place.workspace)}/${place.port}/${place.session}`;
  const text = el("textarea", { placeholder: "Tell the agent…" });
  const stop = el("button", {
    class: "btn no hidden", onclick: async () => {
      try { await api(`${where}/stop`, {}); say("stopped", true); refresh(); }
      catch (error) { say(error.message); }
    },
  }, "stop");
  const send = el("button", {
    class: "btn go", onclick: async () => {
      if (!text.value.trim()) return;
      try { await api(`${where}/message`, { text: text.value }); text.value = ""; place.stick = true; say("sent", true); loadMessages(); }
      catch (error) { say(error.message); }
    },
  }, "send");
  return { head: el("div"), thread: el("div"), text, stop,
    composer: el("div", { class: "composer" }, text, el("div", { class: "btns" }, send, stop)) };
}

function drawSession() {
  const place = state.place;
  const parts = place.parts;
  const workspace = state.overview.workspaces.find((each) => each.name === place.workspace);
  const found = workspace && workspace.servers.flatMap((server) => server.sessions).find((session) => session.id === place.session);
  const busy = found && found.status === "busy";
  parts.head.replaceChildren(kv([["state", el("span", { class: busy ? "good" : "dim" }, busy ? "working" : "idle")],
    ["where", place.workspace]]));
  parts.text.placeholder = busy ? "The agent is working; a message waits for its turn" : "Tell the agent…";
  parts.stop.classList.toggle("hidden", !busy);
  if (!view.contains(parts.composer)) view.replaceChildren(parts.head, parts.thread, parts.composer);
  const typing = parts.thread.contains(document.activeElement) && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
  if (typing) return; // an answer to the agent's question being typed
  const shown = state.messages.map(messageView).filter(Boolean);
  const sent = state.overview.files.filter((file) => file.workspace === place.workspace && found && file.sent * 1000 >= (found.created || 0));
  if (sent.length) shown.push(section("sent to you"), ...sent.map((file) => el("div", { class: "figure" }, fileTile(file))));
  const waiting = waitingBoxes(state.overview, place.workspace);
  if (waiting.length) shown.push(section("waiting for you", waiting.length), ...waiting);
  if (!shown.length) shown.push(el("div", { class: "empty" }, "No message yet."));
  const bottom = document.documentElement.scrollHeight - window.innerHeight;
  const near = window.scrollY >= bottom - 120;
  parts.thread.replaceChildren(...shown);
  if (state.messages.length && (place.stick || near)) {
    place.stick = false;
    window.scrollTo(0, document.documentElement.scrollHeight);
  }
}

function drawStatus(overview) {
  const ready = overview.model.status === "ready";
  const flying = ((overview.agent || {}).requests || []).length > 0;
  status.replaceChildren(
    el("span", { class: ready ? "good" : "bad" }, "● model"), " ",
    el("span", { class: flying ? "acc" : "dim" }, flying ? "● working" : "○ idle"));
  const waiting = waitingBoxes(overview).length;
  waitingCount.textContent = waiting ? `(${waiting})` : "";
}

function draw() {
  if (!state.overview) return;
  drawStatus(state.overview);
  const place = state.place;
  back.classList.toggle("hidden", !place);
  title.textContent = place ? (place.session ? place.title || "session" : place.workspace) : "";
  for (const button of tabs.querySelectorAll("button")) button.classList.toggle("on", button.dataset.tab === state.tab);
  if (place && place.session) return drawSession();
  const typing = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (typing) return; // do not redraw under someone typing a task or an answer
  const parts = place ? workspaceView(state.overview) : state.tab === "work" ? workView(state.overview)
    : state.tab === "files" ? filesView(state.overview) : state.tab === "log" ? logView() : nowView(state.overview);
  view.replaceChildren(...parts);
}

async function refresh() {
  try {
    state.overview = await api("api/overview");
    draw();
  } catch (error) {
    if (error.status === 401) return pairView();
    say(error.message);
  }
}

async function loadMessages() {
  const place = state.place;
  if (!place || !place.session) return;
  try {
    const found = await api(`api/sessions/${encodeURIComponent(place.workspace)}/${place.port}/${place.session}?limit=40`);
    if (state.place === place) { state.messages = found.messages; draw(); }
  } catch (error) { say(error.message); }
}

function openSession(workspace, port, session, name) {
  state.place = { workspace, port, session, title: name, stick: true, from: state.place };
  state.place.parts = sessionParts(state.place);
  state.messages = [];
  draw();
  loadMessages();
}

function openWorkspace(name) {
  state.place = { workspace: name, from: null };
  draw();
  window.scrollTo(0, 0);
}

function pairView() {
  tabs.classList.add("hidden");
  const code = el("input", { placeholder: "XXXX XXXX", autocomplete: "one-time-code", autocapitalize: "characters" });
  view.replaceChildren(el("div", { class: "center" },
    el("div", { class: "brand" }, "◆ CLANK"),
    el("div", {}, "Pair this phone"),
    el("div", { class: "dim" }, "On the computer: Clank's console, F9 (Phone), p. Type the code it shows."),
    code,
    el("div", { class: "btns" }, el("button", {
      class: "btn go", onclick: async () => {
        try { await api("api/pair", { code: code.value }); say("paired", true); start(); }
        catch (error) { say(error.message); }
      },
    }, "pair"))));
}

function tick() {
  clearTimeout(state.timer);
  if (document.visibilityState !== "visible") return;
  refresh().then(() => {
    const place = state.place;
    if (place && place.session) loadMessages();
    const open = place && place.session && state.overview && state.overview.workspaces
      .flatMap((workspace) => workspace.servers).flatMap((server) => server.sessions).find((session) => session.id === place.session);
    const seconds = place && place.session ? (open && open.status === "busy" ? BUSY_SECONDS : IDLE_SECONDS) : NOW_SECONDS;
    state.timer = setTimeout(tick, seconds * 1000);
  });
}

async function start() {
  try {
    await api("api/me");
  } catch (error) {
    if (error.status === 401) return pairView();
    view.replaceChildren(el("div", { class: "center" }, el("div", { class: "brand" }, "◆ CLANK"), el("div", { class: "bad" }, error.message)));
    return;
  }
  tabs.classList.remove("hidden");
  tick();
}

back.addEventListener("click", () => {
  state.place = state.place ? state.place.from : null;
  draw();
  tick();
});
for (const button of tabs.querySelectorAll("button")) {
  button.addEventListener("click", () => {
    state.tab = button.dataset.tab;
    state.place = null;
    draw();
    window.scrollTo(0, 0);
    if (state.tab === "log") loadLog();
  });
}
document.addEventListener("visibilitychange", tick);
start();
