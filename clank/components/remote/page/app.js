// Clank's phone app (design 0025, decision 0143; the page of design 0005 made an installed app): live from one stream
// of events, it shows Now (the model, the machine, what waits for you, what works), Flows (every flow, a flow's screen
// on the Flow view, building one), a session on the conversation stream (the words as the model writes them, the Guide
// and the context as sheets), Work (every workspace and its sessions, a new task), Files (what the agents sent), and
// More (this phone's log of exchanges, settings); says when the stream drops and when the PC cannot be reached; and
// looks like the console: monospace, thin rules, rows to tap. Everything comes from this page's own address; every
// action carries the X-Clank-Phone header. The logic that needs no browser is `model.mjs`.

import {
  RECONNECT_SECONDS, allSessions, applyTalk, boxGlyph, clockText, emptyTalk, failedTalk, flowFilter, lastKnown, linkBadge,
  liveIndex, machineGauges, modelLine, phaseWords, present, runControls, sentTalk, streamState, talkItems, waitingCount,
  workingRows,
} from "./model.mjs";

const view = document.getElementById("view");
const machineLabel = document.getElementById("machine");
const back = document.getElementById("back");
const status = document.getElementById("status");
const tabs = document.getElementById("tabs");
const toast = document.getElementById("toast");
const attention = document.getElementById("attention");
const waitingBadge = document.getElementById("count-now");
const LOG_LIMIT = 100;
const KNOWN = "clank-last-known"; // the offline screen's summary, kept on the phone: names and numbers only
const ATTENTION_SECONDS = 20;

// tab: now, flows, work, files or more; place: a workspace's page, a flow's, a session's or More's log, over the tab;
// overview: the last `now` the stream sent; link: the stream's state; events: the stream's events this visit, newest
// first; talk: the session shown, built from its conversation stream (talkSource).
const state = {
  tab: "now", place: null, overview: null, talk: null, talkSource: null, sessionTimer: null, task: "", files: null,
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

// A node's children replaced by those given, leaving out the empty ones (`present`, model.mjs): replaceChildren writes
// null as the text "null" (the Now screen showed it under the header).
function fill(node, ...children) {
  node.replaceChildren(...present(children.flat()));
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
  view.scrollTo(0, 0);
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

// A session (design 0025 §7) on the conversation stream (design 0023 §3): the header from the readout (the model's
// phase and speed, the window's share), the conversation's items (the owner's words, the model's text, its thinking
// folded with its length, each call one line that opens on its result, a failed step, a compaction; the live item marked
// LIVE while the session works), what waits in the session answered in place, and a composer whose message shows at
// once as pending. The Guide and the Context open as sheets over the composer; every action is the device's.
const SHEET_ITEMS = 8; // the biggest items the Context sheet lists
const GUIDE_WORDS = { stop: "now; the files stay", note: "read at the next step", compact: "at the next step" };

// A session's page keeps its composer from the moment it opens: the redraws change the conversation above it, never
// the box being typed in (a phone's keyboard would close).
function sessionParts(place) {
  const text = el("textarea", { placeholder: "Tell the agent…" });
  const where = `api/sessions/${encodeURIComponent(place.workspace)}/${place.port}/${place.session}`;
  const send = el("button", {
    class: "btn go", onclick: async () => {
      const words = text.value.trim();
      if (!words) return;
      const id = `pending-${Date.now()}`;
      state.talk = sentTalk(state.talk, id, words);
      text.value = "";
      place.stick = true;
      drawSession();
      try { await api(`${where}/message`, { text: words }); say("sent", true); }
      catch (error) {
        const [back, talk] = failedTalk(state.talk, id);
        state.talk = talk;
        if (!text.value) text.value = back;
        say(error.message);
        drawSession();
      }
    },
  }, "send");
  const stop = el("button", { class: "btn no hidden", onclick: () => guideAct(place, { action: "stop", title: "Stop", confirm: false }) }, "stop");
  const guide = el("button", { class: "btn", onclick: () => openSheet(place, "guide") }, "Guide");
  const context = el("button", { class: "btn", onclick: () => openSheet(place, "context") }, "Context");
  return { head: el("div"), thread: el("div"), text, stop, context, sheet: el("div", { class: "sheet hidden" }),
    composer: el("div", { class: "composer" }, text, el("div", { class: "btns" }, send, stop, guide, context)) };
}

function openSession(workspace, port, session, name) {
  closeSession();
  state.place = { workspace, port, session, title: name, stick: true, from: state.place, open: {}, sheet: null, guide: null, context: null };
  state.place.parts = sessionParts(state.place);
  state.talk = emptyTalk();
  draw();
  view.scrollTo(0, 0);
  followSession();
}

// The conversation stream of the session shown: opened when its screen opens and when the app comes back to the front,
// closed when the screen closes; the browser resumes it from the last event it saw (Last-Event-ID), and a stream the
// browser gave up on is opened again after a few seconds while the screen still shows.
function followSession() {
  const place = state.place;
  if (!place || !place.session || document.visibilityState !== "visible" || state.talkSource) return;
  const query = `workspace=${encodeURIComponent(place.workspace)}&session=${encodeURIComponent(place.session)}&limit=40`;
  const source = new EventSource(`api/conversation/stream?${query}`);
  state.talkSource = source;
  for (const name of ["snapshot", "message", "part", "delta", "removed", "status", "waiting", "readout", "session"]) {
    source.addEventListener(name, (message) => {
      if (state.place !== place) return;
      const id = /^\d+$/.test(message.lastEventId) ? Number(message.lastEventId) : undefined;
      state.talk = applyTalk(state.talk, name, JSON.parse(message.data), id);
      scheduleSessionDraw();
    });
  }
  const again = () => {
    if (state.talkSource === source) state.talkSource = null;
    setTimeout(() => { if (state.place === place) followSession(); }, RECONNECT_SECONDS * 1000);
  };
  source.addEventListener("closing", () => { source.close(); again(); });
  source.addEventListener("error", () => {
    if (source.readyState === EventSource.CLOSED) again(); // else the browser tries again by itself, from the last event
  });
}

function closeSession() {
  if (state.talkSource) { state.talkSource.close(); state.talkSource = null; }
  if (state.sessionTimer) cancelAnimationFrame(state.sessionTimer);
  state.sessionTimer = null;
}

// The deltas come many times a second: the screen is drawn once a frame.
function scheduleSessionDraw() {
  if (state.sessionTimer) return;
  state.sessionTimer = requestAnimationFrame(() => { state.sessionTimer = null; if (state.place && state.place.session) drawSession(); });
}

function shareWords(context) {
  return context && context.window && context.used !== null && context.used !== undefined
    ? `${Math.round((context.used / context.window) * 100)}%` : "";
}

// The header's line from the readout while the session works: its phase, its speed, the window's share.
function sessionHead(place) {
  const talk = state.talk;
  const session = talk.conversation && talk.conversation.session;
  const readout = talk.readout || {};
  const now = readout.now || {};
  const busy = session ? session.busy : false;
  const doing = busy ? (phaseWords(now.phase) || "working") : session ? "idle" : "connecting…";
  const speed = busy && now.speed && now.speed.now ? `${Math.round(now.speed.now)} tok/s` : "";
  const share = shareWords(readout.context) || (place.context ? shareWords(place.context) : "");
  const rows = [["state", el("span", { class: busy ? "good" : "dim" }, [doing, speed].filter(Boolean).join(" · "))],
    ["where", `${place.workspace}${session && session.title ? " · " + session.title : place.title ? " · " + place.title : ""}`]];
  if (share) rows.push(["context", `${share} of the window${readout.slot && readout.slot.title ? " · " + readout.slot.title : ""}`]);
  return kv(rows);
}

function openSheet(place, which) {
  place.sheet = place.sheet === which ? null : which;
  drawSession();
  if (place.sheet === "guide") loadGuide(place);
  if (place.sheet === "context") loadContext(place);
}

async function loadGuide(place) {
  try {
    const found = await api(`api/guide/${encodeURIComponent(place.workspace)}/${encodeURIComponent(place.session)}`);
    if (state.place === place) { place.guide = found; drawSession(); }
  } catch (error) { if (state.place === place) { place.guide = { missing: error.message }; drawSession(); } }
}

async function loadContext(place) {
  try {
    const found = await api(`api/context/${encodeURIComponent(place.workspace)}/${encodeURIComponent(place.session)}`);
    if (state.place === place) { place.context = found; drawSession(); }
  } catch (error) { if (state.place === place) { place.context = { missing: error.message }; drawSession(); } }
}

// An action of the Guide, the device's: Stop at once, the others once more confirmed as the offer says; Note sends the
// composer's text; Undo sends the revert the offer names and what it takes back; Pause resumes while paused; Drop goes
// to the Context sheet, where each result has its own. The Guide is read again after.
async function guideAct(place, action, body = {}) {
  const where = `api/guide/${encodeURIComponent(place.workspace)}/${encodeURIComponent(place.session)}`;
  let route = action.action;
  if (action.action === "note") {
    const words = place.parts.text.value.trim();
    if (!words) { say("type the note in the box first"); return; }
    body = { text: words };
  } else if (action.action === "undo") {
    if (action.mode === "redo") route = "redo";
    else body = { message: action.revert.message, part: action.revert.part, steps: action.takes.steps.filter((n) => n !== null), said: action.takes.said };
  } else if (action.action === "pause" && action.paused) route = "resume";
  if (action.action === "drop" && !body.part) { openSheet(place, "context"); return; }
  const cost = action.cost && action.cost.words ? ` ${action.cost.words}.` : "";
  if (action.confirm && !window.confirm(`${action.title}: ${action.brief || ""}.${cost}`)) return;
  try {
    await api(`${where}/${route}`, body);
    if (action.action === "note") place.parts.text.value = "";
    say(`${action.title.toLowerCase()}: asked`, true);
  } catch (error) { say(error.message); }
  if (place.sheet === "guide") loadGuide(place);
  if (place.sheet === "context") loadContext(place);
}

function stateWords(found) {
  if (!found || !found.state) return "";
  return [found.state, found.by, found.time ? ago(found.time) + " ago" : "", found.why].filter(Boolean).join(" · ");
}

// The Guide sheet (design 0012 §9 on the phone): each action a button with its title, what it does in brief and what it
// costs; disabled with why when it cannot run now; its last run's state under it.
function guideSheet(place) {
  const guide = place.guide;
  const parts = [el("div", { class: "sheet-head" }, el("span", {}, "the Guide"), el("button", { class: "btn small", onclick: () => openSheet(place, null) }, "close"))];
  if (!guide) return [...parts, el("div", { class: "empty" }, "Reading…")];
  if (guide.missing) return [...parts, el("div", { class: "empty" }, guide.missing)];
  for (const action of guide.actions) {
    const words = action.action === "pause" ? action.brief : GUIDE_WORDS[action.action] ? `${action.brief} · ${GUIDE_WORDS[action.action]}` : action.brief;
    const last = stateWords(action.state);
    parts.push(el("div", { class: "action" + (action.can ? "" : " off") },
      el("div", { class: "btns" },
        el("button", { class: "btn small" + (action.action === "stop" ? " no" : ""), disabled: action.can ? null : "disabled",
          onclick: () => guideAct(place, action) }, action.title),
        el("span", { class: "muted" }, words)),
      action.can ? null : el("div", { class: "dim" }, action.why),
      action.cost && action.cost.words ? el("div", { class: "dim" }, action.cost.words) : null,
      last ? el("div", { class: "dim" }, `last: ${last}`) : null));
  }
  parts.push(el("div", { class: "btns" }, el("button", { class: "btn small", onclick: () => loadGuide(place) }, "read again")));
  return parts;
}

// The Context sheet (design 0012 §4 on the phone): the window used of the whole with the compaction line, what fills it
// (each part's share), the biggest items with Drop for a finished call's result.
function contextSheet(place) {
  const context = place.context;
  const parts = [el("div", { class: "sheet-head" }, el("span", {}, "the context"), el("button", { class: "btn small", onclick: () => openSheet(place, null) }, "close"))];
  if (!context) return [...parts, el("div", { class: "empty" }, "Reading…")];
  if (context.missing) return [...parts, el("div", { class: "empty" }, context.missing)];
  const window_ = context.window;
  const used = context.used;
  const share = shareWords(context);
  const line = context.line && window_ ? `compacts at ${Math.round((context.line / window_) * 100)}%` : "";
  const rows = [["window", window_ ? `${window_.toLocaleString()} tokens` : "not known"],
    ["used", used !== null && used !== undefined ? `${used.toLocaleString()} tokens${share ? " · " + share : ""}` : "not measured yet"]];
  if (line) rows.push(["rule", `${line}${context.left !== null && context.left !== undefined ? " · " + context.left.toLocaleString() + " left" : ""}`]);
  if (context.slot && context.slot.title) rows.push(["model", context.slot.title]);
  parts.push(kv(rows));
  if (share) {
    const full = Math.min(100, Math.round((used / window_) * 100));
    parts.push(el("div", { class: "bar wide" }, el("i", { class: full > 80 ? "bad" : full > 60 ? "warn" : "", style: `width:${full}%` })));
  }
  const estimate = context.parts;
  if (!estimate) { parts.push(el("div", { class: "empty" }, "What fills it is counted at the session's next step.")); return parts; }
  parts.push(section("what fills it"));
  for (const part of estimate.parts || []) {
    parts.push(el("div", { class: "share" },
      el("span", { class: "k" }, part.label), el("span", { class: "v" }, `${part.tokens.toLocaleString()} · ${Math.round(part.share * 100)}%`),
      el("div", { class: "bar" }, el("i", { style: `width:${Math.round(part.share * 100)}%` }))));
  }
  const items = (estimate.items || []).slice(0, SHEET_ITEMS);
  if (items.length) parts.push(section("the biggest items", items.length));
  for (const item of items) {
    const what = [item.step ? `step ${item.step}` : "", item.tool || item.what || item.part, `${item.tokens.toLocaleString()} tokens`].filter(Boolean).join(" · ");
    const mark = item.cleared ? el("span", { class: "dim" }, item.cleared_by ? `cleared by ${item.cleared_by}` : "cleared")
      : item.node ? el("button", { class: "btn small", onclick: () => guideAct(place, { action: "drop", title: "Drop", confirm: true,
        brief: `clears ${what}'s result`, cost: null }, { part: item.node }) }, "Drop") : null;
    parts.push(el("div", { class: "btns item" }, el("span", { class: "muted" }, what), mark));
  }
  return parts;
}

// One item of the conversation; a call opens on its result when tapped, the thinking on its words.
function itemView(item, place, live) {
  const open = place.open[item.id];
  const toggle = () => { place.open[item.id] = !open; drawSession(); };
  const tag = live ? el("span", { class: "live-mark" }, "LIVE") : null;
  if (item.kind === "text") return el("div", { class: "text" }, rich(item.text), tag);
  if (item.kind === "thinking") {
    return el("div", { class: "fold" + (open ? " open" : "") },
      el("div", { class: "tool", onclick: toggle }, `· thought · ${item.length.toLocaleString()} characters · ${open ? "hide" : "show"}`, tag),
      open ? el("pre", {}, item.text) : null);
  }
  if (item.kind === "call") {
    const mark = item.status === "completed" ? "✓" : item.status === "error" ? "✗" : "…";
    const kind = item.status === "error" ? " error" : item.status === "completed" ? " done" : "";
    const facts = [item.chars ? size(item.chars) : "", item.seconds !== null ? `${item.seconds} s` : ""].filter(Boolean).join(" · ");
    return el("div", { class: "fold" + (open ? " open" : "") },
      el("div", { class: "tool" + kind, onclick: toggle }, `${mark} ${item.line}${facts ? "  · " + facts : ""}`, tag),
      open ? el("pre", {}, item.error || item.output || `(${item.status})`) : null);
  }
  if (item.kind === "error") return el("div", { class: "tool error" }, `✗ ${item.text}`, tag);
  if (item.kind === "compaction") return el("div", { class: "tool" }, "— compacted: the model reads a summary of what came before —");
  return null;
}

// The conversation as blocks: one per message, headed by who spoke; the pending messages as the owner's, dimmed.
function threadView(place) {
  const items = talkItems(state.talk);
  const live = liveIndex(state.talk, items);
  const blocks = [];
  let block = null;
  items.forEach((item, index) => {
    if (item.kind === "owner" || item.kind === "notice") {
      const who = item.kind === "notice" ? el("div", { class: "who agent" }, "◆ clank") : el("div", { class: "who you" }, item.pending ? "› you · sending…" : item.about ? `› you · ${item.about}` : "› you");
      const body = item.kind === "notice" ? el("div", {}, el("strong", {}, item.title), el("div", { class: "dim" }, item.detail)) : rich(item.text);
      blocks.push(el("div", { class: "msg" + (item.pending ? " pending" : "") }, who, body));
      block = null;
      return;
    }
    if (!block || block.dataset.message !== item.message) {
      block = el("div", { class: "msg" });
      block.dataset.message = item.message;
      block.append(el("div", { class: "who agent" }, "◆ agent"));
      blocks.push(block);
    }
    const shown = itemView(item, place, index === live);
    if (shown) block.append(shown);
  });
  return blocks;
}

function drawSession() {
  const place = state.place;
  const parts = place.parts;
  const talk = state.talk;
  const session = talk.conversation && talk.conversation.session;
  const busy = Boolean(session && session.busy);
  parts.head.replaceChildren(sessionHead(place));
  parts.text.placeholder = busy ? "The agent is working; a message waits for its turn" : "Tell the agent…";
  parts.stop.classList.toggle("hidden", !busy);
  const share = shareWords((talk.readout || {}).context) || (place.context ? shareWords(place.context) : "");
  parts.context.textContent = share ? `Context ${share}` : "Context";
  parts.sheet.classList.toggle("hidden", !place.sheet);
  if (place.sheet) fill(parts.sheet, place.sheet === "guide" ? guideSheet(place) : contextSheet(place));
  if (!view.contains(parts.composer)) view.replaceChildren(parts.head, parts.thread, parts.composer, parts.sheet);
  const typing = parts.thread.contains(document.activeElement) && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
  if (typing) return;
  const shown = threadView(place);
  const waiting = state.overview ? waitingBoxes(state.overview, place.workspace) : [];
  if (waiting.length) shown.push(section("waiting for you", waiting.length), ...waiting);
  if (!shown.length) shown.push(el("div", { class: "empty" }, talk.conversation ? "No message yet." : "Connecting to the session…"));
  const near = view.scrollTop >= view.scrollHeight - view.clientHeight - 120;
  fill(parts.thread, shown);
  if (talk.conversation && (place.stick || near)) {
    place.stick = false;
    view.scrollTop = view.scrollHeight;
  }
}

// The header: the PC's name, the stream's state, the count of what waits.
function drawHeader() {
  const link = streamState(state.link, Date.now());
  machineLabel.textContent = location.hostname.split(".")[0] || "";
  const badge = linkBadge(link);
  status.replaceChildren(el("span", { class: badge.kind }, badge.words));
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
  fill(view, paused, parts);
}

function openWorkspace(name) {
  state.place = { workspace: name, from: null };
  draw();
  view.scrollTo(0, 0);
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
    el("button", { onclick: () => { state.tab = "now"; state.place = null; attention.classList.add("hidden"); draw(); view.scrollTo(0, 0); } }, "Open"));
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
  source.addEventListener("connected", () => {
    state.link.connected = true;
    if (!state.overview) launchStep("Connected · waiting for the PC's first reading…");
    draw();
  });
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

// The column fills the screen by itself (style.css, the app shell); while the keyboard is up (a field has the focus and
// the visible part is much shorter than the page) it follows the visible part instead, and the tab bar steps aside.
function fitView() {
  const seen = window.visualViewport;
  const field = document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  const up = Boolean(seen) && field && window.innerHeight - seen.height > 120;
  const root = document.documentElement.style;
  if (up) {
    root.setProperty("--view-height", `${Math.round(seen.height)}px`);
    root.setProperty("--view-top", `${Math.round(seen.offsetTop)}px`);
  }
  document.body.classList.toggle("keyboard", up);
}

// The launch screen (index.html) says what the app waits for: the step it is at, how long it has waited and, past a
// few seconds, why it may be slow; under it the last known summary kept on the phone (names and numbers only).
const launchedAt = Date.now();

function launchStep(words) {
  const step = document.getElementById("launch-step");
  if (step) step.textContent = words;
}

function launchTick() {
  const time = document.getElementById("launch-time");
  if (!time) return;
  const seconds = Math.floor((Date.now() - launchedAt) / 1000);
  time.textContent = seconds < 3 ? "" : seconds < 12 ? `${seconds} s`
    : `${seconds} s · the PC answers slowly: Clank's service may be busy reading the workspaces`;
}

function launchKnown() {
  const launch = document.getElementById("launch");
  const known = state.known;
  if (!launch || !known || launch.querySelector(".known")) return;
  launch.append(el("div", { class: "known" },
    el("div", { class: "dim" }, `Last known · ${clock(known.at)}, ${ago(known.at)} ago`),
    el("div", {}, known.model),
    el("div", {}, `${known.waiting} waiting for you`),
    ...known.working.map((line) => el("div", {}, line))));
}

async function start() {
  if (location.search.includes("claim=")) history.replaceState(null, "", location.pathname); // the claim is spent
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { /* an older iOS: the app still runs */ });
  launchStep("Reaching the PC through Tailscale…");
  launchKnown();
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
  launchStep("Paired · reading what runs on the PC…");
  tabs.classList.remove("hidden");
  stream();
}

back.addEventListener("click", () => {
  closeSession();
  state.place = state.place ? state.place.from || null : null;
  draw();
  followSession();
});
for (const button of tabs.querySelectorAll("button")) {
  button.addEventListener("click", () => {
    closeSession();
    state.tab = button.dataset.tab;
    state.place = null;
    draw();
    view.scrollTo(0, 0);
    if (state.tab === "files") loadFiles();
    if (state.tab === "flows") loadFlows();
  });
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") { if (!state.link.source) stream(); followSession(); }
  else { closeSession(); if (state.link.source) { state.link.source.close(); state.link.source = null; } }
});
setInterval(() => {
  if (document.hidden) return;
  drawHeader();
  if (!state.overview) launchTick();
  if (streamState(state.link, Date.now()).state !== "live") draw();
}, 1000);
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", fitView);
  window.visualViewport.addEventListener("scroll", fitView);
}
window.addEventListener("resize", fitView);
document.addEventListener("focusin", fitView);
document.addEventListener("focusout", () => setTimeout(fitView, 60));
fitView();
start();
