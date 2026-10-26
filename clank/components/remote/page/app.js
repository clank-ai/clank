// Clank's phone app (design 0025, decision 0143; the page of design 0005 made an installed app): live from one stream
// of events, it shows Now (the model, the machine, what waits for you, what works), Flows (what waits in them; the Flow
// view comes with the next step), Work (every workspace and its sessions, a new task), Files (what the agents sent),
// and More (this phone's log of exchanges, settings); says when the stream drops and when the PC cannot be reached;
// and looks like the console: monospace, thin rules, rows to tap. Everything comes from this page's own address;
// every action carries the X-Clank-Phone header. The logic that needs no browser is `model.mjs`.

import {
  RECONNECT_SECONDS, allSessions, boxGlyph, clockText, flowFilter, lastKnown, machineGauges, modelLine, runControls,
  streamState, waitingCount, workingRows,
} from "./model.mjs";

const view = document.getElementById("view");
const machineLabel = document.getElementById("machine");
const back = document.getElementById("back");
const status = document.getElementById("status");
const tabs = document.getElementById("tabs");
const toast = document.getElementById("toast");
const attention = document.getElementById("attention");
const waitingBadge = document.getElementById("count-now");
const BUSY_SECONDS = 2;
const IDLE_SECONDS = 8;
const LOG_LIMIT = 100;
const KNOWN = "clank-last-known"; // the offline screen's summary, kept on the phone: names and numbers only
const ATTENTION_SECONDS = 20;

// tab: now, flows, work, files or more; place: a workspace's page, a session's or More's log, over the tab; overview:
// the last `now` the stream sent; link: the stream's state; events: the stream's events this visit, newest first.
const state = {
  tab: "now", place: null, overview: null, messages: [], timer: null, task: "", files: null,
  log: { items: [], open: {} }, notes: {}, reads: {}, events: [], known: null,
  flows: { rows: null, plannings: {}, filter: "all", view: null, building: false, timer: null },
  link: { connected: false, failedSince: null, tries: 0, lastEventAt: null, source: null },
};
try { state.known = JSON.parse(localStorage.getItem(KNOWN) || "null"); } catch { state.known = null; }

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function say(text, ok = false) {
  toast.textContent = text;
  toast.className = `toast ${ok ? "ok" : ""}`;
  clearTimeout(say.timer);
  say.timer = setTimeout(() => toast.classList.add("hidden"), ok ? 1500 : 4000);
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Clank-Phone": "1" }, body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = new Error((data && data.error) || `${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function ago(when) {
  if (!when) return "";
  const seconds = Math.max(0, (Date.now() - new Date(typeof when === "number" ? when * 1000 : when).getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} d`;
}
function size(bytes) { return bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`; }
function clock(when) { return new Date(when).toLocaleTimeString([], { hour12: false }); }

// Markdown's small part: fenced code, inline code, bold, paragraphs.
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

function sessionRow(session) {
  const busy = session.status === "busy";
  return row({
    glyph: busy ? "●" : "○", glyphClass: busy ? "good" : "dim", line: session.title || "a session",
    sub: `${session.workspace} · ${busy ? "working" : "idle"}`, meta: ago(session.updated),
    onclick: () => openSession(session.workspace, session.port, session.id, session.title),
  });
}

// Now's top: the model, what it does, its speed; then the machine as four gauges (design 0025 §5).
function hero(overview) {
  const line = modelLine(overview);
  const dot = el("span", { class: "dot " + (line.ready ? "good" : line.status === "starting" ? "warn" : "bad") }, "●");
  const doing = [line.doing ? el("span", { class: "acc" }, line.doing) : null, line.detail, line.speed].filter(Boolean);
  const parts = [];
  doing.forEach((part, index) => { if (index) parts.push(" · "); parts.push(part); });
  const tiles = machineGauges(overview.machine).map((gauge) => el("div", { class: "gauge-tile" },
    el("span", { class: "k" }, gauge.label), el("span", { class: "v" }, gauge.text),
    el("div", { class: "bar" }, el("i", { class: gauge.fraction > 0.9 ? "bad" : gauge.fraction > 0.7 ? "warn" : "",
      style: `width:${Math.round(Math.min(1, gauge.fraction) * 100)}%` }))));
  return el("div", { class: "hero" },
    el("div", { class: "big" }, dot, line.title, el("span", { class: "dim" }, ` · ${line.status}`)),
    el("div", { class: "doing" }, parts.length ? parts : el("span", { class: "dim" }, "nothing in flight")),
    tiles.length ? el("div", { class: "gauges" }, tiles) : null);
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
        try { await api("api/marks/seen", { ids: [mark.id] }); say("seen", true); }
        catch (error) { say(error.message); }
      },
    }, "seen")));
}

// What waits: OpenCode's permissions and questions (in one workspace, or in all), the Monitor's marks told to the phone,
// and Clank's own questions. The stream's next `now` takes an answered one off the list.
function waitingBoxes(overview, only = null) {
  const boxes = [];
  for (const workspace of overview.workspaces) {
    if (only && workspace.name !== only) continue;
    for (const server of workspace.servers) {
      for (const asked of server.permissions) {
        const diff = asked.metadata && (asked.metadata.diff || asked.metadata.command);
        const reply = (answer) => async () => {
          try { await api(`api/permissions/${encodeURIComponent(workspace.name)}/${server.port}/${asked.id}`, { reply: answer }); say("replied", true); }
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
          try { await api(`api/questions/${encodeURIComponent(workspace.name)}/${server.port}/${asked.id}`, { answers }); say("answered", true); }
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
    if (question.flow) { boxes.push(flowBox(question)); continue; }
    boxes.push(el("div", { class: "box waiting" },
      el("div", { class: "head" }, `clank · ${question.title}`), question.detail ? el("pre", {}, question.detail) : null,
      el("div", { class: "btns" }, question.options.map((option) => el("button", {
        class: "btn small", onclick: async () => {
          try { await api(`api/clank-questions/${question.id}`, { option: option.id }); say("answered", true); }
          catch (error) { say(error.message); }
        },
      }, option.label)))));
  }
  return boxes;
}

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

// Now (design 0025 §5): the model and the machine, what waits for you, what works now.
function nowView(overview) {
  const parts = [hero(overview)];
  const waiting = waitingBoxes(overview);
  parts.push(section("waiting for you", waiting.length));
  parts.push(...(waiting.length ? waiting : [el("div", { class: "empty" }, "Nothing waits for you.")]));
  const working = workingRows(overview);
  parts.push(section("working now", working.length));
  parts.push(...(working.length ? working.map(sessionRow) : [el("div", { class: "empty" }, "Nothing works now.")]));
  for (const workspace of overview.workspaces.filter((each) => each.problem)) {
    parts.push(el("div", { class: "box" }, el("span", { class: "warn" }, `${workspace.name}: `), workspace.problem));
  }
  return parts;
}

// Flows (design 0025 §6): the list from the service's summaries (each flow's state in a word and in words), filtered;
// a flow's screen from the Flow view's JSON (design 0013 §12), as the console draws it; both read again when a
// flows.* or question.* event arrives on the stream, once per burst.
const FILTER_WORDS = { all: "All", running: "Running", waits: "Waits", ended: "Ended" };
const FLOW_GLYPHS = {
  waits: ["!", "warn"], running: ["●", "good"], building: ["…", "good"], paused: ["‖", "warn"], queued: ["○", "dim"],
  done: ["✓", "dim"], stopped: ["✗", "dim"], never: ["○", "dim"],
};

async function loadFlows() {
  try {
    const found = await api("api/flows");
    state.flows.rows = found.flows;
    state.flows.plannings = found.plannings || {};
    if (state.tab === "flows" && !(state.place && state.place.flow)) draw();
  } catch (error) { say(error.message); }
}

async function loadFlow() {
  const place = state.place;
  if (!place || !place.flow) return;
  const { workspace, name } = place.flow;
  try {
    const found = await api(`api/flows/${encodeURIComponent(workspace)}/${encodeURIComponent(name)}`);
    if (state.place !== place) return;
    const shown = state.flows.view;
    if (shown && !shown.missing && shown.version === found.version && shown.flow === found.flow) return;
    state.flows.view = found;
    draw();
  } catch (error) {
    if (state.place === place) { state.flows.view = { missing: error.message }; draw(); }
  }
}

function flowsChanged() {
  clearTimeout(state.flows.timer);
  state.flows.timer = setTimeout(() => {
    if (state.place && state.place.flow) loadFlow();
    if (state.tab === "flows") loadFlows();
  }, 300);
}

function openFlow(workspace, name) {
  state.place = { flow: { workspace, name }, from: state.place };
  state.flows.view = null;
  draw();
  window.scrollTo(0, 0);
  loadFlow();
}

function flowsView(overview) {
  const flows = state.flows;
  const parts = [buildBox(overview)];
  parts.push(el("div", { class: "chips" }, Object.keys(FILTER_WORDS).map((which) => el("button", {
    class: "chip" + (flows.filter === which ? " on" : ""), onclick: () => { flows.filter = which; draw(); },
  }, FILTER_WORDS[which]))));
  if (flows.rows === null) { parts.push(el("div", { class: "empty" }, "Reading…")); return parts; }
  const shown = flowFilter(flows.rows, flows.filter);
  parts.push(section("flows", shown.length));
  if (!shown.length) {
    parts.push(el("div", { class: "empty" }, flows.rows.length
      ? "No flow in this filter." : "No flow yet: build one with the model, or write its file (clank flow new)."));
  }
  for (const line of shown) parts.push(flowRow(line));
  return parts;
}

function flowRow(line) {
  const [glyph, glyphClass] = FLOW_GLYPHS[line.state] || ["○", "dim"];
  const sub = [line.words, line.workspace, line.model].filter(Boolean).join(" · ");
  return row({ glyph, glyphClass, line: line.title, sub, meta: line.time ? ago(line.time) : "",
    onclick: () => openFlow(line.workspace, line.name) });
}

// Build a flow: a planning opened in Clank's VS Code window on the PC, in a running workspace (design 0013 §15).
function buildBox(overview) {
  const flows = state.flows;
  const running = overview.workspaces.filter((workspace) => workspace.state === "running" && !workspace.problem);
  const close = el("button", { class: "btn small", onclick: () => { flows.building = false; draw(); } }, "cancel");
  if (!flows.building) {
    return el("div", { class: "btns" },
      el("button", { class: "btn go", onclick: () => { flows.building = true; draw(); } }, "Build a flow"));
  }
  if (!running.length) {
    return el("div", { class: "box" }, el("div", {}, "No workspace runs: open one on the computer, then build a flow here."),
      el("div", { class: "btns" }, close));
  }
  const choice = el("select", {}, running.map((workspace) => el("option", { value: workspace.name }, workspace.name)));
  const name = el("input", { placeholder: "its name (empty: the first free)", autocapitalize: "none" });
  return el("div", { class: "box" },
    el("div", { class: "head" }, "build a flow with the model"),
    el("div", { class: "dim" }, "The planning opens in Clank's VS Code window on the PC: talk it through there, or from its session here once it starts."),
    running.length > 1 ? choice : el("div", {}, `in ${running[0].name}`), name,
    el("div", { class: "btns" },
      el("button", { class: "btn go", onclick: async () => {
        const workspace = running.length > 1 ? choice.value : running[0].name;
        try {
          const opened = await api("api/flows/new", { workspace, name: name.value.trim() });
          flows.building = false;
          say(opened.window === "waits" ? "planning opened: it waits for Clank's VS Code window on the PC"
            : "planning opened in Clank's VS Code window on the PC", true);
          loadFlows();
        } catch (error) { say(error.message); }
      } }, "open the planning"), close));
}

// A flow (design 0025 §6): its run's words and the controls its state allows, what it waits for, its planning while it
// is built, its proposals, its boxes as a column with the running box open, what lies ahead, its deliverables.
function flowScreen(overview) {
  const found = state.flows.view;
  const place = state.place.flow;
  if (!found) return [el("div", { class: "empty" }, "Reading…")];
  if (found.missing) return [el("div", { class: "empty" }, found.missing)];
  const run = found.run;
  const where = `api/flows/${encodeURIComponent(place.workspace)}/${encodeURIComponent(place.name)}`;
  const act = (action) => async () => {
    try {
      await api(`${where}/${action}`, {});
      say(action === "run" ? "started" : `${action}${action.endsWith("e") ? "d" : "ped"}`, true);
      loadFlow();
      loadFlows();
    } catch (error) { say(error.message); }
  };
  const facts = [["flow", found.title], ["where", found.workspace], ["run", runWords(run)]];
  if (run) facts.push(["since", `${ago(run.created)} ago`]);
  const parts = [kv(facts)];
  const words = { pause: "Pause after this box", resume: "Resume", stop: "Stop", run: "Run" };
  parts.push(el("div", { class: "btns" }, runControls(run).map((control) => el("button", {
    class: "btn" + (control === "stop" ? " no" : control === "pause" ? "" : " go"),
    onclick: act(control === "resume" ? "run" : control),
  }, words[control]))));
  const waiting = overview.questions.filter((question) => question.flow && question.flow.flow === found.flow).map(flowBox);
  if (waiting.length) parts.push(section("waiting for you", waiting.length), ...waiting);
  if (found.planning) parts.push(...planningParts(found.planning));
  if (found.proposals && found.proposals.items && found.proposals.items.length) parts.push(...proposalParts(found, where));
  parts.push(section("boxes", (found.boxes || []).length));
  for (const box of found.boxes || []) parts.push(...boxParts(box));
  if (found.ahead && found.ahead.length) {
    parts.push(section("ahead", found.ahead.length));
    for (const next of found.ahead) parts.push(row({ glyph: "›", line: titleOf(found, next.box), sub: next.costs.join(" · ") }));
  }
  if (found.deliverables && found.deliverables.length) {
    parts.push(section("deliverables", found.deliverables.length));
    for (const file of found.deliverables) {
      const sub = [titleOf(found, file.box), file.try ? `try ${file.try}` : "", file.present === false ? "not in the folder" : ""];
      parts.push(row({ glyph: file.passed === true ? "✓" : file.passed === false ? "✗" : "·",
        glyphClass: file.passed === false ? "bad" : file.passed ? "good" : "dim", line: file.path, sub: sub.filter(Boolean).join(" · ") }));
    }
  }
  if (found.built) parts.push(section("built with the model"), el("div", { class: "dim" }, builtWords(found.built)));
  return parts;
}

function titleOf(found, id) {
  const box = (found.boxes || []).find((each) => each.id === id);
  return box ? box.title : id;
}

function runWords(run) {
  if (!run) return "not run yet";
  if (run.status === "queued") return `queued${run.behind ? " behind " + run.behind.split("/").pop() : ""}`;
  if (run.status === "done" || run.status === "stopped") return run.status;
  if (run.waiting) return `waits for you · ${run.waiting.kind}`;
  return run.paused ? "paused" : `running · run ${run.number}`;
}

function builtWords(built) {
  return Object.entries(built).filter(([, value]) => typeof value === "string" && value)
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${value}`).join(" · ") || "built with the model";
}

// A planning (design 0013 §15): its state, where it opens, its steps so far, and its session once it started.
function planningParts(planning) {
  const tone = (kind) => kind === "failed" ? "bad" : kind === "waiting" || kind === "waits" ? "warn" : "dim";
  const place = planning.where === "vscode" ? "in Clank's VS Code window on the PC"
    : planning.where === "attach" ? planning.attach : "in the terminal that asked";
  return [section("building with the model"), el("div", { class: "box" },
    el("div", { class: "head" }, `${planning.title || planning.name} · ${planning.status}`),
    planning.why ? el("div", { class: "warn" }, planning.why) : null,
    el("div", { class: "dim" }, place),
    el("div", { class: "steps" }, (planning.steps || []).map((step) => el("div", { class: "step" },
      el("span", { class: tone(step.kind) }, step.kind), " ", step.said,
      step.at ? el("span", { class: "dim" }, ` · ${ago(step.at)} ago`) : null))),
    planning.session ? el("div", { class: "btns" }, el("button", { class: "btn small",
      onclick: () => openSession(planning.session.workspace, planning.session.port, planning.session.session, planning.title),
    }, "its session")) : null)];
}

// The proposals of the run's batch (design 0013 §9): each with Accept and Reject while it waits; all at once.
function proposalParts(found, where) {
  const batch = found.proposals;
  const waiting = batch.waiting || [];
  const decide = (decision, body) => async () => {
    try { await api(`${where}/proposals/${decision}`, body); say(`${decision}ed`, true); loadFlow(); }
    catch (error) { say(error.message); }
  };
  const parts = [section(`proposals · from ${titleOf(found, batch.box)}`, waiting.length)];
  if (batch.summary) parts.push(el("div", { class: "dim" }, batch.summary));
  for (const item of batch.items) {
    const open = item.state === "proposed";
    parts.push(el("div", { class: "box" + (open ? " waiting" : "") },
      el("div", { class: "head" }, `${item.id} · ${item.type} · ${item.title}`),
      el("div", { class: "dim" }, [item.why, item.preset_title, item.mode].filter(Boolean).join(" · ")),
      item.prompt ? el("div", { class: "muted" }, item.prompt.split("\n")[0]) : null,
      item.writes && item.writes.length ? el("div", { class: "dim" }, `writes ${item.writes.join(", ")}`) : null,
      open ? el("div", { class: "btns" },
        el("button", { class: "btn ok small", onclick: decide("accept", { proposals: [item.id] }) }, "Accept"),
        el("button", { class: "btn no small", onclick: decide("reject", { proposals: [item.id] }) }, "Reject"))
        : el("div", { class: "dim" }, item.state)));
  }
  if (waiting.length > 1) {
    parts.push(el("div", { class: "btns" },
      el("button", { class: "btn ok", onclick: decide("accept", { all: true }) }, "Accept all"),
      el("button", { class: "btn no", onclick: decide("reject", { all: true }) }, "Reject all")));
  }
  return parts;
}

// A box in the column: its glyph, type, model, tries and when it ended; the running one open with its session.
function boxParts(box) {
  const tries = box.tries || [];
  const last = tries[tries.length - 1];
  const sub = [box.type, box.preset_title, tries.length ? `try ${tries.length}${box.cap ? " of " + box.cap : ""}` : "",
    box.ended ? `${ago(box.ended)} ago` : "", box.asks ? "asks you" : ""];
  const parts = [row({ glyph: boxGlyph(box), glyphClass: box.state === "running" ? "good" : box.state === "failed" ? "bad" : box.asks ? "warn" : "dim",
    line: box.title, sub: sub.filter(Boolean).join(" · ") })];
  if (box.state === "running" && last) {
    const written = (last.written || []).map((file) => (typeof file === "string" ? file : file.path));
    parts.push(el("div", { class: "box open-box" },
      el("div", { class: "dim" }, [last.tokens ? `${last.tokens.toLocaleString()} tokens` : "", `since ${ago(last.started)}`, last.agent, last.mode].filter(Boolean).join(" · ")),
      written.length ? el("div", { class: "dim" }, `wrote ${written.join(", ")}`) : null,
      last.session && last.session.session ? el("div", { class: "btns" }, el("button", { class: "btn small",
        onclick: () => openSession(last.session.workspace, last.session.port, last.session.session, box.title) }, "Session")) : null));
  }
  if (box.state === "failed" && box.why) parts.push(el("div", { class: "box" }, el("span", { class: "bad" }, "✗ "), box.why));
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
  const recent = allSessions(overview).slice(0, 8);
  if (recent.length) parts.push(section("sessions"), ...recent.map(sessionRow));
  parts.push(section("new task"), taskBox(overview.workspaces));
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

async function loadFiles() {
  try { state.files = (await api("api/files")).files || []; draw(); }
  catch (error) { say(error.message); }
}

function filesView() {
  if (state.files === null) return [el("div", { class: "empty" }, "Reading…")];
  if (!state.files.length) return [el("div", { class: "empty" }, "Nothing sent yet. Ask an agent to send you a figure.")];
  return [section("sent to you", state.files.length), el("div", { class: "files" }, state.files.map(fileTile))];
}

// The log: what this phone asked and what it was sent, newest first; an exchange opens whole when tapped.
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
  const parts = [section("this phone and the PC", state.log.items.length),
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

// The stream's events this visit, newest first: what happened, with its time and whether it asked for attention.
function eventsView() {
  const parts = [section("events this visit", state.events.length)];
  for (const event of state.events.slice(0, 60)) {
    parts.push(row({ glyph: event.attention ? "!" : "·", glyphClass: event.attention ? "warn" : "dim", line: event.title,
      sub: `${clock(event.time)} · ${event.type}` }));
  }
  if (!state.events.length) parts.push(el("div", { class: "empty" }, "Nothing happened yet since the app opened."));
  return parts;
}

// More: the log, the events, this phone and the PC; the rest of design 0025 §9 comes with its step.
function moreView() {
  const link = streamState(state.link, Date.now());
  const last = state.link.lastEventAt ? `last event ${ago(state.link.lastEventAt)} ago` : "no event yet";
  return [
    section("more"),
    row({ glyph: "›", line: "Activity", sub: `events this visit: ${state.events.length}`, onclick: () => { state.place = { more: "events" }; draw(); } }),
    row({ glyph: "›", line: "This phone's log", sub: "every exchange with the PC, whole", onclick: () => { state.place = { more: "log" }; draw(); loadLog(); } }),
    section("the PC"),
    kv([["address", location.host], ["through", "Tailscale · tailnet only"], ["stream", `${link.state} · ${last}`],
      ["app", "updates with Clank on the PC"]]),
    section("this phone"),
    el("div", { class: "btns" }, el("button", { class: "btn no", onclick: async () => {
      try { await api("api/signout", {}); location.reload(); } catch (error) { say(error.message); }
    } }, "sign out: this phone forgets its pairing")),
  ];
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

// A session's page keeps its composer from the moment it opens: the redraws change the conversation above it, never the
// box being typed in (a phone's keyboard would close).
function sessionParts(place) {
  const where = `api/sessions/${encodeURIComponent(place.workspace)}/${place.port}/${place.session}`;
  const text = el("textarea", { placeholder: "Tell the agent…" });
  const stop = el("button", {
    class: "btn no hidden", onclick: async () => {
      try { await api(`${where}/stop`, {}); say("stopped", true); }
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
  if (typing) return;
  const shown = state.messages.map(messageView).filter(Boolean);
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

// The header: the PC's name, the stream's state, the count of what waits.
function drawHeader() {
  const link = streamState(state.link, Date.now());
  machineLabel.textContent = location.hostname.split(".")[0] || "";
  const words = link.state === "live" ? "● live" : link.state === "reconnecting" ? `● reconnecting ${clockText(link.pausedSeconds)}` : "● offline";
  status.replaceChildren(el("span", { class: link.state }, words));
  const waiting = state.overview ? waitingCount(state.overview) : 0;
  waitingBadge.textContent = waiting ? `(${waiting})` : "";
}

// The screen for when the PC cannot be reached (design 0025 §3): what was tried, what to check, the last known state.
function offlineView() {
  const link = streamState(state.link, Date.now());
  const known = state.known;
  return [el("div", { class: "offline" },
    el("h2", {}, "Can't reach the PC"),
    el("div", { class: "why" }, "Is Tailscale on? Is the PC awake?"),
    kv([["this iPhone", navigator.onLine ? "online" : "offline"],
      [location.hostname.split(".")[0] || "the PC", `didn't answer · ${link.tries} ${link.tries === 1 ? "try" : "tries"}, the last ${clockText(link.pausedSeconds % RECONNECT_SECONDS)} ago`]]),
    el("div", { class: "muted" }, "Tailscale on this iPhone: an app can't see it. Open Tailscale and check it says Connected. The PC asleep or off: Clank can't wake it from here."),
    el("div", { class: "btns" }, el("button", { class: "btn go", onclick: () => stream(true) }, "Try again"),
      el("span", { class: "dim" }, ` next try in ${link.nextTryIn} s`)),
    known ? el("div", { class: "known" },
      el("div", { class: "dim" }, `Last known · ${clock(known.at)}, ${ago(known.at)} ago`),
      el("div", {}, known.model),
      el("div", {}, `${known.waiting} waiting for you`),
      ...known.working.map((line) => el("div", {}, line)),
      el("div", { class: "dim" }, "Kept on this iPhone: names and numbers only.")) : null)];
}

function draw() {
  drawHeader();
  const link = streamState(state.link, Date.now());
  const place = state.place;
  back.classList.toggle("hidden", !place);
  for (const button of tabs.querySelectorAll("button")) button.classList.toggle("on", button.dataset.tab === state.tab);
  if (link.state === "offline" && !state.overview) { view.replaceChildren(...offlineView()); return; }
  if (!state.overview) return;
  view.classList.toggle("stale", link.state !== "live");
  if (link.state === "offline") { view.className = ""; view.replaceChildren(...offlineView()); return; }
  if (place && place.session) return drawSession();
  const typing = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (typing) return;
  const paused = link.state === "reconnecting"
    ? el("div", { class: "paused" }, `Live updates paused ${clockText(link.pausedSeconds)}. Below: as of ${state.known ? clock(state.known.at) : "a moment ago"}.`) : null;
  const parts = place && place.more === "log" ? logView() : place && place.more === "events" ? eventsView()
    : place && place.flow ? flowScreen(state.overview)
    : place ? workspaceView(state.overview) : state.tab === "flows" ? flowsView(state.overview) : state.tab === "work" ? workView(state.overview)
    : state.tab === "files" ? filesView() : state.tab === "more" ? moreView() : nowView(state.overview);
  view.replaceChildren(paused, ...parts);
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
  followSession();
}

function openWorkspace(name) {
  state.place = { workspace: name, from: null };
  draw();
  window.scrollTo(0, 0);
}

// A session's messages are read every few seconds while its page shows (the conversation stream comes with the next
// step of design 0025); everything else moves with the live stream.
function followSession() {
  clearTimeout(state.timer);
  const place = state.place;
  if (!place || !place.session || document.visibilityState !== "visible") return;
  const open = state.overview && allSessions(state.overview).find((session) => session.id === place.session);
  const seconds = open && open.status === "busy" ? BUSY_SECONDS : IDLE_SECONDS;
  state.timer = setTimeout(() => { loadMessages().then(followSession); }, seconds * 1000);
}

function pairView() {
  tabs.classList.add("hidden");
  const code = el("input", { placeholder: "XXXX XXXX", autocomplete: "one-time-code", autocapitalize: "characters" });
  view.replaceChildren(el("div", { class: "center" },
    el("div", { class: "brand" }, "◆ CLANK"),
    el("div", {}, "Pair this phone"),
    el("div", { class: "dim" }, "On the computer: Clank's console, F9 (Phone), p. Scan the QR it shows, or type the code under it here."),
    code,
    el("div", { class: "btns" }, el("button", {
      class: "btn go", onclick: async () => {
        try { await api("api/pair", { code: code.value }); say("paired", true); start(); }
        catch (error) { say(error.message); }
      },
    }, "pair"))));
}

// An event that asks for attention shows as a line under the header while it is fresh; Open goes to Now.
function noticed(event) {
  if (!event.attention) return;
  attention.replaceChildren(el("span", { class: "what" }, event.title),
    el("button", { onclick: () => { state.tab = "now"; state.place = null; attention.classList.add("hidden"); draw(); window.scrollTo(0, 0); } }, "Open"));
  attention.classList.remove("hidden");
  clearTimeout(noticed.timer);
  noticed.timer = setTimeout(() => attention.classList.add("hidden"), ATTENTION_SECONDS * 1000);
}

// The live stream (design 0025 §3): `now` draws the app, each `event` is kept and may ask for attention; a drop is said
// in the header, then the offline screen after thirty seconds; the browser resumes it from the last event it saw.
function stream(again = false) {
  if (state.link.source) { state.link.source.close(); state.link.source = null; }
  if (again) { state.link.failedSince = null; state.link.tries = 0; draw(); }
  const source = new EventSource("api/stream");
  state.link.source = source;
  source.addEventListener("open", () => {
    state.link.connected = true; state.link.failedSince = null; state.link.tries = 0; drawHeader();
  });
  source.addEventListener("connected", () => { state.link.connected = true; draw(); });
  source.addEventListener("now", (message) => {
    state.overview = JSON.parse(message.data);
    state.link.connected = true; state.link.failedSince = null; state.link.tries = 0;
    state.link.lastEventAt = Date.now();
    state.known = lastKnown(state.overview, Date.now());
    try { localStorage.setItem(KNOWN, JSON.stringify(state.known)); } catch { /* storage may be refused: the screen still draws */ }
    draw();
  });
  source.addEventListener("event", (message) => {
    const event = JSON.parse(message.data);
    state.link.lastEventAt = Date.now();
    state.events.unshift(event);
    if (state.events.length > 500) state.events.length = 500;
    noticed(event);
    if (event.type.startsWith("flows.") || event.type.startsWith("question.")) flowsChanged();
    if (state.place && state.place.more === "events") draw();
  });
  source.addEventListener("reset", () => { say("the PC pruned events while this phone was away: shown afresh"); });
  source.addEventListener("closing", () => { source.close(); state.link.source = null; state.link.connected = false; state.link.failedSince = Date.now(); draw(); });
  source.addEventListener("error", () => {
    if (state.link.connected || state.link.failedSince === null) state.link.failedSince = Date.now();
    state.link.connected = false;
    state.link.tries += 1;
    if (source.readyState === EventSource.CLOSED) { // the browser gave up (a 401, a 403): pair again, or wait
      state.link.source = null;
      api("api/me").catch((error) => { if (error.status === 401) pairView(); });
    }
    draw();
  });
}

async function start() {
  if (location.search.includes("claim=")) history.replaceState(null, "", location.pathname); // the claim is spent
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { /* an older iOS: the app still runs */ });
  try {
    await api("api/me");
  } catch (error) {
    if (error.status === 401) return pairView();
    state.link.failedSince = state.link.failedSince || Date.now();
    state.link.tries += 1;
    view.replaceChildren(...offlineView());
    setTimeout(start, RECONNECT_SECONDS * 1000);
    return;
  }
  tabs.classList.remove("hidden");
  stream();
}

back.addEventListener("click", () => {
  state.place = state.place ? state.place.from || null : null;
  draw();
  followSession();
});
for (const button of tabs.querySelectorAll("button")) {
  button.addEventListener("click", () => {
    state.tab = button.dataset.tab;
    state.place = null;
    draw();
    window.scrollTo(0, 0);
    if (state.tab === "files") loadFiles();
    if (state.tab === "flows") loadFlows();
  });
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") { if (!state.link.source) stream(); followSession(); }
  else { clearTimeout(state.timer); if (state.link.source) { state.link.source.close(); state.link.source = null; } }
});
setInterval(() => { if (!document.hidden) drawHeader(); if (!document.hidden && streamState(state.link, Date.now()).state !== "live") draw(); }, 1000);
start();
