// A board's page (design 0022 §3): draws the board the extension sends, and turns what the owner does into edits (set,
// add and remove operations, `BoardCore` deciding them as the extension would) sent back to be written to the file.
// Items are elements placed in the world's pixels; the world is moved and zoomed as one (the wheel pans, Ctrl and the
// wheel zoom at the pointer, Space or the middle button drags). Select, move (snapping to other items' edges and centers,
// else the grid), resize (a figure keeps its aspect), select by a box, align; the toolbar's tools make notes, LaTeX,
// frames, slots, highlights and pins (a drag sizes them, a click gives their kind's size), draw with the pen and draw
// arrows between items; a double click edits in place. The selection's bar aligns, frames, deletes and asks the agent.
// Files dropped from VS Code's Explorer and images pasted become figures; text pasted becomes a note.
(function () {
  "use strict";
  const vscode = acquireVsCodeApi();
  const Core = window.BoardCore;
  const $ = (id) => document.getElementById(id);
  const viewport = $("viewport");
  const world = $("world");
  const itemsEl = $("items");
  const marksEl = $("mark-paths");
  const selectionEl = $("selection");
  const guidesEl = $("guides");
  const marquee = $("marquee");
  const bar = $("bar");
  const askBox = $("ask");
  const SVG = "http://www.w3.org/2000/svg";
  const BOXED = new Set(["figure", "latex", "note", "slot", "frame", "highlight"]);
  const RESIZABLE = new Set(["figure", "latex", "note", "slot", "frame", "highlight"]);
  const MIN_ZOOM = 0.1;
  const MAX_ZOOM = 4;
  const state = vscode.getState() || {};
  let board = null;
  let path = "";
  let uris = {};
  let compiled = {};
  let view = state.view || { x: 60, y: 60, zoom: 1 };
  let fitted = Boolean(state.view);
  let selected = new Set();
  let tool = "select";
  let gesture = null;
  let spaceHeld = false;
  let editing = null;
  let said = "";

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key === "style") Object.assign(node.style, value);
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
    return node;
  }

  function svg(tag, attributes) {
    const node = document.createElementNS(SVG, tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    return node;
  }

  const escaped = (text) => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  if (window.marked) {
    window.marked.use({ renderer: { html: (token) => escaped(typeof token === "string" ? token : token.text) } });
  }
  const MATH = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g;

  /** Markdown with its math drawn by KaTeX (math set aside first, so its underscores stay math). */
  function markdown(text) {
    const math = [];
    const kept = String(text).replace(MATH, (whole, display, bracket, inline, paren) => {
      math.push({ text: display ?? bracket ?? inline ?? paren, display: display !== undefined || bracket !== undefined });
      return `@@MATH${math.length - 1}@@`;
    });
    const html = window.marked ? window.marked.parse(kept) : escaped(kept);
    return html.replace(/@@MATH(\d+)@@/g, (whole, index) => {
      const piece = math[Number(index)];
      return piece && window.katex
        ? window.katex.renderToString(piece.text, { displayMode: piece.display, throwOnError: false })
        : whole;
    });
  }

  function itemById(id, from = board) {
    return from ? from.items.find((each) => each.id === id) : undefined;
  }

  // -- the view

  function toWorld(event) {
    const rect = viewport.getBoundingClientRect();
    return { x: (event.clientX - rect.left - view.x) / view.zoom, y: (event.clientY - rect.top - view.y) / view.zoom };
  }

  function toScreen(x, y) {
    return { x: x * view.zoom + view.x, y: y * view.zoom + view.y };
  }

  function applyView() {
    world.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`;
    const step = (board?.settings?.grid || 20) * view.zoom;
    viewport.style.backgroundSize = `${step}px ${step}px`;
    viewport.style.backgroundPosition = `${view.x}px ${view.y}px`;
    $("zoom-level").textContent = `${Math.round(view.zoom * 100)} %`;
    vscode.setState({ ...state, view });
    drawSelection();
  }

  function zoomAt(factor, sx, sy) {
    const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.zoom * factor));
    view = { x: sx - ((sx - view.x) * zoom) / view.zoom, y: sy - ((sy - view.y) * zoom) / view.zoom, zoom };
    applyView();
  }

  function bounds(items) {
    const boxes = items.map((each) => Core.boxOf(each)).filter(Boolean);
    if (!boxes.length) return null;
    const left = Math.min(...boxes.map((b) => b.x));
    const top = Math.min(...boxes.map((b) => b.y));
    return { x: left, y: top, w: Math.max(...boxes.map((b) => b.x + b.w)) - left, h: Math.max(...boxes.map((b) => b.y + b.h)) - top };
  }

  function fit(items = board?.items || []) {
    const box = bounds(items);
    const width = viewport.clientWidth || 800;
    const height = viewport.clientHeight || 600;
    if (!box) {
      view = { x: 60, y: 60, zoom: 1 };
    } else {
      const zoom = Math.min(1.5, Math.max(MIN_ZOOM, Math.min((width - 120) / Math.max(box.w, 1), (height - 120) / Math.max(box.h, 1))));
      view = { zoom, x: (width - box.w * zoom) / 2 - box.x * zoom, y: (height - box.h * zoom) / 2 - box.y * zoom + 12 };
    }
    applyView();
  }

  // -- drawing

  function placeStyle(item) {
    return { left: `${item.x}px`, top: `${item.y}px`, width: `${item.w}px`, height: `${item.h}px` };
  }

  function drawItem(item, pins) {
    const base = { class: `item ${item.kind}`, "data-id": item.id };
    switch (item.kind) {
      case "figure": {
        const uri = uris[item.file];
        return el("div", { ...base, style: placeStyle(item), title: item.file },
          el("div", { class: "picture" }, uri ? el("img", { src: uri, alt: item.caption || item.file, draggable: "false" })
            : el("span", { class: "missing", text: `${item.file} is not in the folder` })),
          item.caption ? el("div", { class: "caption", text: item.caption }) : null);  // prettier-ignore
      }
      case "latex": {
        const paper = el("div", { class: "paper" });
        const art = compiled[item.id];
        if (item.mode === "compiled") {
          if (art?.uri) paper.append(el("img", { src: art.uri, alt: item.source }));
          else paper.append(el("span", { class: "missing", text: art?.error ? "" : "Compiling with TeX…" }));
          if (art?.error) paper.append(el("div", { class: "problem", text: art.error }));
        } else {
          const math = el("div", { class: "math" });
          math.innerHTML = window.katex
            ? window.katex.renderToString(String(item.source || ""), { displayMode: true, throwOnError: false })
            : escaped(item.source || "");
          paper.append(math);
        }
        paper.append(el("span", { class: "tag", text: item.mode === "compiled" ? "TeX" : "math" }));
        return el("div", { ...base, style: placeStyle(item) }, paper);
      }
      case "note": {
        const node = el("div", { ...base, style: placeStyle(item) });
        node.innerHTML = item.text ? markdown(item.text) : '<p style="opacity:.6">Double-click to write</p>';
        return node;
      }
      case "frame":
        return el("div", { ...base, style: placeStyle(item) },
          el("div", { class: "frame-name" }, el("b", { text: item.name || "Frame" }), item.export?.file ? ` · ${item.export.file}` : " · frame"));  // prettier-ignore
      case "slot":
        return el("div", { ...base, class: `item slot ${item.state === "filling" ? "filling" : ""}`, style: placeStyle(item) },
          el("b", { text: item.label || "a figure" }),
          el("span", { class: "hint", text: item.state === "filling" ? "The agent is making this figure" : "A place for the agent to fill" }),
          item.state === "filling" ? null : el("button", { class: "text", "data-act": "fill", text: "Fill" }));  // prettier-ignore
      case "highlight":
        return el("div", { ...base, style: placeStyle(item) });
      case "pin": {
        const number = pins.indexOf(item.id) + 1;
        return el("div", { ...base, class: `item pin ${item.open === false ? "answered" : ""}`, style: { left: `${item.x}px`, top: `${item.y}px` } },
          el("span", { class: "pin-dot", text: String(number) }),
          item.text ? el("span", { class: "pin-text", text: item.text }) : null);  // prettier-ignore
      }
      default:
        return null;
    }
  }

  function edgePoint(box, toward) {
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h / 2;
    const dx = toward.x - cx;
    const dy = toward.y - cy;
    if (!dx && !dy) return { x: cx, y: cy };
    const scale = 1 / Math.max(Math.abs(dx) / Math.max(box.w / 2, 1), Math.abs(dy) / Math.max(box.h / 2, 1));
    return { x: cx + dx * scale + Math.sign(dx) * 4, y: cy + dy * scale + Math.sign(dy) * 4 };
  }

  function endPoint(end, from) {
    if (end?.item) {
      const item = itemById(end.item, from);
      const box = item && Core.boxOf(item);
      if (box) return { box };
    }
    return { point: { x: Number(end?.x ?? 0), y: Number(end?.y ?? 0) } };
  }

  function arrowLine(item, from) {
    const a = endPoint(item.from, from);
    const b = endPoint(item.to, from);
    const center = (end) => (end.box ? { x: end.box.x + end.box.w / 2, y: end.box.y + end.box.h / 2 } : end.point);
    const start = a.box ? edgePoint(a.box, center(b)) : a.point;
    const finish = b.box ? edgePoint(b.box, center(a)) : b.point;
    return { start, finish };
  }

  function drawMarks(from = board) {
    marksEl.replaceChildren();
    for (const item of from?.items || []) {
      if (item.kind === "pen" && item.points?.length) {
        const d = item.points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
        marksEl.append(svg("path", { d, "data-id": item.id, class: selected.has(item.id) ? "chosen" : "" }));
      } else if (item.kind === "arrow") {
        const { start, finish } = arrowLine(item, from);
        marksEl.append(svg("line", {
          x1: start.x, y1: start.y, x2: finish.x, y2: finish.y, "data-id": item.id,
          class: `arrow ${selected.has(item.id) ? "chosen" : ""}`, "marker-end": "url(#arrow-head)",
        }));  // prettier-ignore
      }
    }
  }

  function fitMath() {
    for (const node of itemsEl.querySelectorAll(".item.latex .math")) {
      const paper = node.parentElement;
      node.style.transform = "";
      const scale = Math.min(2, (paper.clientWidth - 16) / Math.max(node.offsetWidth, 1), (paper.clientHeight - 12) / Math.max(node.offsetHeight, 1));
      node.style.transform = `scale(${Math.max(0.2, scale)})`;
    }
  }

  function render() {
    itemsEl.replaceChildren();
    const empty = $("empty");
    if (empty) empty.remove();
    if (!board) return;
    const pins = board.items.filter((each) => each.kind === "pin").map((each) => each.id);
    for (const item of board.items) {
      const node = drawItem(item, pins);
      if (node) itemsEl.append(node);
    }
    if (!board.items.length) {
      viewport.append(el("div", { id: "empty", class: "empty" }, el("b", { text: board.title || "An empty board" }),
        "Pick a tool above, drop a figure from the Explorer, paste an image, or ask the agent to place figures here."));  // prettier-ignore
    }
    drawMarks();
    fitMath();
    drawSelection();
    const open = board.items.filter((each) => each.kind === "pin" && each.open !== false).length;
    const send = $("send-pins");
    send.hidden = !open;
    send.textContent = open === 1 ? "Send 1 pin to the agent" : `Send ${open} pins to the agent`;
    $("status").textContent = said || `${board.items.length} item${board.items.length === 1 ? "" : "s"} · saved`;
  }

  /** Positions only (while a move or a resize is under way): the items' boxes, the marks and the selection. */
  function placeItems(from) {
    for (const item of from.items) {
      const node = itemsEl.querySelector(`[data-id="${item.id}"]`);
      if (!node) continue;
      if (item.kind === "pin") Object.assign(node.style, { left: `${item.x}px`, top: `${item.y}px` });
      else if (BOXED.has(item.kind)) Object.assign(node.style, placeStyle(item));
    }
    drawMarks(from);
    drawSelection(from);
  }

  function drawSelection(from = board) {
    selectionEl.replaceChildren();
    if (!from) return positionBar();
    const chosen = [...selected].map((id) => itemById(id, from)).filter(Boolean);
    const pad = 4 / view.zoom;
    for (const item of chosen) {
      const box = Core.boxOf(item);
      if (!box || item.kind === "arrow") continue;
      const size = item.kind === "pin" ? 14 / view.zoom : 0;
      selectionEl.append(el("div", { class: "outline", style: {
        left: `${box.x - pad - size}px`, top: `${box.y - pad - size}px`, width: `${box.w + 2 * (pad + size)}px`,
        height: `${box.h + 2 * (pad + size)}px`, borderWidth: `${1.5 / view.zoom}px`,
      } }));  // prettier-ignore
    }
    if (chosen.length === 1 && RESIZABLE.has(chosen[0].kind)) {
      const box = Core.boxOf(chosen[0]);
      const size = 9 / view.zoom;
      const spots = { nw: [0, 0], n: [0.5, 0], ne: [1, 0], e: [1, 0.5], se: [1, 1], s: [0.5, 1], sw: [0, 1], w: [0, 0.5] };
      for (const [handle, [fx, fy]] of Object.entries(spots)) {
        selectionEl.append(el("div", { class: "handle", "data-handle": handle, "data-for": chosen[0].id, style: {
          left: `${box.x + fx * box.w - size / 2}px`, top: `${box.y + fy * box.h - size / 2}px`, width: `${size}px`,
          height: `${size}px`, borderWidth: `${1.5 / view.zoom}px`, cursor: `${handle}-resize`,
        } }));  // prettier-ignore
      }
    }
    positionBar(from);
  }

  function positionBar(from = board) {
    const chosen = [...selected].map((id) => itemById(id, from)).filter(Boolean);
    if (!chosen.length || gesture || editing || !askBox.hidden) {
      bar.hidden = true;
      return;
    }
    const box = bounds(chosen);
    if (!box) {
      bar.hidden = true;
      return;
    }
    const top = toScreen(box.x, box.y);
    const boxed = chosen.filter((each) => BOXED.has(each.kind)).length;
    for (const button of bar.querySelectorAll("[data-align]")) button.disabled = boxed < 2;
    bar.querySelector('[data-act="frame"]').hidden = !boxed;
    bar.hidden = false;
    const rect = viewport.getBoundingClientRect();
    bar.style.left = `${Math.max(8, Math.min(rect.width - bar.offsetWidth - 8, top.x))}px`;
    bar.style.top = `${Math.max(8, top.y - bar.offsetHeight - 14) + rect.top}px`;
  }

  function drawGuides(guides) {
    guidesEl.replaceChildren();
    for (const guide of guides || []) {
      const at = guide.axis === "x" ? toScreen(guide.at, 0).x : toScreen(0, guide.at).y;
      guidesEl.append(guide.axis === "x"
        ? svg("line", { x1: at, y1: 0, x2: at, y2: viewport.clientHeight })
        : svg("line", { x1: 0, y1: at, x2: viewport.clientWidth, y2: at }));  // prettier-ignore
    }
  }

  // -- edits

  function send(ops, note) {
    if (!ops.length || !board) return;
    board = Core.applyOps(board, ops);
    said = note || "";
    render();
    vscode.postMessage({ type: "ops", ops });
  }

  function removeSelected() {
    const ids = [...selected];
    if (!ids.length) return;
    const gone = new Set(ids);
    for (const item of board.items) {
      if (item.kind === "arrow" && (gone.has(item.from?.item) || gone.has(item.to?.item))) gone.add(item.id);
    }
    selected.clear();
    send([{ op: "remove", ids: [...gone] }]);
  }

  function duplicate() {
    const copies = [];
    let from = board;
    for (const id of selected) {
      const item = itemById(id);
      if (!item || item.kind === "arrow") continue;
      const copy = Core.newItem(from, item.kind, 0, 0, {});
      const fields = { ...item, id: copy.id, by: "owner" };
      if (item.kind === "pen") fields.points = item.points.map(([x, y]) => [x + 20, y + 20]);
      else Object.assign(fields, { x: item.x + 20, y: item.y + 20 });
      copies.push({ op: "add", item: fields });
      from = Core.applyOps(from, [{ op: "add", item: fields }]);
    }
    if (!copies.length) return;
    selected = new Set(copies.map((op) => op.item.id));
    send(copies);
  }

  function frameSelected() {
    const chosen = [...selected].map((id) => itemById(id)).filter((each) => each && BOXED.has(each.kind));
    const box = bounds(chosen);
    if (!box) return;
    const frame = Core.newItem(board, "frame", box.x - 20, box.y - 40, { w: box.w + 40, h: box.h + 60, name: "Figure" });
    selected = new Set([frame.id]);
    send([{ op: "add", item: frame }]);
    startEdit(frame.id);
  }

  function setTool(name) {
    tool = name;
    for (const button of document.querySelectorAll(".tool[data-tool]")) button.classList.toggle("on", button.dataset.tool === name);
    viewport.className = `viewport tool-${name}`;
  }

  // -- editing in place

  function screenBox(item) {
    const box = Core.boxOf(item);
    const corner = toScreen(box.x, box.y);
    return { x: corner.x, y: corner.y, w: box.w * view.zoom, h: box.h * view.zoom };
  }

  function startEdit(id) {
    commitEdit();
    const item = itemById(id);
    if (!item) return;
    const box = screenBox(item);
    const place = (width, height, below) => ({
      left: `${Math.max(8, Math.min(viewport.clientWidth - width - 8, box.x))}px`,
      top: `${Math.max(8, below ? box.y + box.h + 8 : box.y)}px`, width: `${width}px`, minHeight: height ? `${height}px` : "",
    });  // prettier-ignore
    let node;
    let read;
    if (item.kind === "note" || item.kind === "pin") {
      const area = el("textarea", { rows: item.kind === "pin" ? 3 : 8 });
      area.value = item.text || "";
      node = el("div", { class: "editor", style: place(Math.max(280, box.w), 0, item.kind === "pin") }, area,
        el("div", { class: "row" }, item.kind === "pin" ? "A comment for the agent" : "Markdown, with $math$",
           el("span", { class: "end" }, el("button", { class: "text primary", text: "Done", onclick: () => commitEdit() }))));  // prettier-ignore
      read = () => ({ text: area.value });
      setTimeout(() => area.focus(), 0);
    } else if (item.kind === "latex") {
      const area = el("textarea", { class: "code", rows: 5 });
      area.value = item.source || "";
      let mode = item.mode === "compiled" ? "compiled" : "math";
      const preview = el("div", { class: "preview" });
      const show = () => {
        if (mode === "math" && window.katex) preview.innerHTML = window.katex.renderToString(area.value || "\\;", { displayMode: true, throwOnError: false });
        else preview.textContent = "Compiled with the folder's TeX when you are done.";
      };
      const modes = el("div", { class: "segmented" });
      for (const [name, label] of [["math", "Math, at once"], ["compiled", "Compiled with TeX"]]) {
        modes.append(el("button", { text: label, class: mode === name ? "on" : "", onclick: (event) => {
          mode = name;
          for (const each of modes.children) each.classList.toggle("on", each === event.currentTarget);
          show();
        } }));  // prettier-ignore
      }
      area.addEventListener("input", show);
      node = el("div", { class: "editor", style: place(Math.max(380, box.w), 0, true) }, modes, area, preview,
        el("div", { class: "row" }, "Ctrl+Enter is done", el("span", { class: "end" },
          el("button", { class: "text", text: "Cancel", onclick: () => cancelEdit() }),
          el("button", { class: "text primary", text: "Done", onclick: () => commitEdit() }))));  // prettier-ignore
      read = () => ({ source: area.value, mode });
      show();
      setTimeout(() => area.focus(), 0);
    } else {
      const field = { figure: "caption", slot: "label", frame: "name" }[item.kind];
      if (!field) return;
      const input = el("input", { value: item[field] || "", placeholder: { caption: "A caption", label: "The figure that goes here", name: "Its name" }[field] });
      node = el("div", { class: "editor", style: place(Math.max(240, Math.min(box.w, 420)), 0, item.kind !== "frame") }, input);
      read = () => ({ [field]: input.value });
      setTimeout(() => {
        input.focus();
        input.select();
      }, 0);
    }
    node.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Escape") cancelEdit();
      if (event.key === "Enter" && (event.ctrlKey || (node.querySelector("input") && !event.shiftKey))) {
        event.preventDefault();
        commitEdit();
      }
    });
    viewport.append(node);
    editing = { id, node, read };
    positionBar();
  }

  function cancelEdit() {
    if (!editing) return;
    editing.node.remove();
    editing = null;
    viewport.focus();
    positionBar();
  }

  function commitEdit() {
    if (!editing) return;
    const { id, node, read } = editing;
    const fields = read();
    node.remove();
    editing = null;
    const item = itemById(id);
    if (!item) return;
    const changed = Object.entries(fields).some(([key, value]) => item[key] !== value);
    if (changed) send([{ op: "set", id, fields }]);
    if (item.kind === "note") {
      requestAnimationFrame(() => {
        const shown = itemsEl.querySelector(`[data-id="${id}"]`);
        if (shown && shown.scrollHeight > shown.clientHeight + 2) send([{ op: "set", id, fields: { h: Math.ceil(shown.scrollHeight + 4) } }]);
      });
    }
    viewport.focus();
  }

  // -- asking the agent

  function openAsk() {
    const ids = [...selected];
    if (!ids.length) return;
    const chips = $("ask-chips");
    chips.replaceChildren(...ids.map((id) => {
      const item = itemById(id);
      const what = item.file || item.label || item.name || item.source || item.text || item.kind;
      return el("span", { text: `${id} · ${String(what).split("\n")[0].slice(0, 32)}` });
    }));  // prettier-ignore
    askBox.hidden = false;
    bar.hidden = true;
    const box = bounds(ids.map((id) => itemById(id)).filter(Boolean));
    const corner = toScreen(box.x, box.y + box.h);
    const rect = viewport.getBoundingClientRect();
    askBox.style.left = `${Math.max(8, Math.min(rect.width - 456, corner.x))}px`;
    askBox.style.top = `${Math.min(rect.height - 140, corner.y + 12) + rect.top}px`;
    $("ask-text").value = "";
    $("ask-text").focus();
  }

  function closeAsk() {
    askBox.hidden = true;
    positionBar();
  }

  function sendAsk() {
    const text = $("ask-text").value.trim();
    if (!text) return;
    vscode.postMessage({ type: "ask", ids: [...selected], text });
    closeAsk();
  }

  // -- gestures

  function itemAt(event) {
    const node = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-id]");
    return node && !node.closest(".handle") ? node.getAttribute("data-id") : undefined;
  }

  viewport.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".editor")) return;
    if (editing) commitEdit();
    if (event.target.closest('[data-act="fill"]')) return;
    viewport.focus();
    const at = toWorld(event);
    const last = { x: event.clientX, y: event.clientY };
    if (event.button === 1 || spaceHeld || tool === "hand") {
      gesture = { kind: "pan", last };
      viewport.classList.add("panning");
    } else if (event.button !== 0) {
      return;
    } else if (tool === "select") {
      const handle = event.target.closest("[data-handle]");
      const id = event.target.closest("[data-id]")?.getAttribute("data-id");
      if (handle) {
        gesture = { kind: "resize", id: handle.dataset.for, handle: handle.dataset.handle, start: at, item: itemById(handle.dataset.for) };
      } else if (id) {
        if (event.shiftKey) {
          if (selected.has(id)) selected.delete(id);
          else selected.add(id);
        } else if (!selected.has(id)) {
          selected = new Set([id]);
        }
        gesture = { kind: "move", start: at, ids: [...selected], moved: false, shift: { dx: 0, dy: 0 } };
      } else {
        if (!event.shiftKey) selected = new Set();
        gesture = { kind: "marquee", start: at, keep: new Set(selected), from: last };
      }
      drawMarks();
      drawSelection();
    } else if (tool === "pen") {
      gesture = { kind: "pen", points: [[Math.round(at.x), Math.round(at.y)]] };
    } else if (tool === "arrow") {
      const id = event.target.closest("[data-id]")?.getAttribute("data-id");
      gesture = { kind: "arrow", from: id ? { item: id } : { x: Math.round(at.x), y: Math.round(at.y) }, start: at };
    } else if (tool === "pin") {
      const pin = Core.newItem(board, "pin", Math.round(at.x), Math.round(at.y));
      selected = new Set([pin.id]);
      send([{ op: "add", item: pin }]);
      setTool("select");
      startEdit(pin.id);
      return;
    } else {
      gesture = { kind: "create", tool, start: at, from: last };
    }
    viewport.setPointerCapture(event.pointerId);
    positionBar();
  });

  viewport.addEventListener("pointermove", (event) => {
    if (!gesture) return;
    const at = toWorld(event);
    switch (gesture.kind) {
      case "pan":
        view = { ...view, x: view.x + event.clientX - gesture.last.x, y: view.y + event.clientY - gesture.last.y };
        gesture.last = { x: event.clientX, y: event.clientY };
        applyView();
        break;
      case "move": {
        const dx = at.x - gesture.start.x;
        const dy = at.y - gesture.start.y;
        if (!gesture.moved && Math.hypot(dx, dy) * view.zoom < 3) return;
        gesture.moved = true;
        const snapped = event.altKey ? { dx: Math.round(dx), dy: Math.round(dy), guides: [] } : Core.snapMove(board, gesture.ids, dx, dy, view.zoom);
        gesture.shift = snapped;
        placeItems(Core.applyOps(board, Core.moveOps(board, gesture.ids, snapped.dx, snapped.dy)));
        drawGuides(snapped.guides);
        break;
      }
      case "resize": {
        const box = Core.resize(gesture.item, gesture.handle, at.x - gesture.start.x, at.y - gesture.start.y);
        gesture.box = { x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.w), h: Math.round(box.h) };
        placeItems(Core.applyOps(board, [{ op: "set", id: gesture.id, fields: gesture.box }]));
        break;
      }
      case "marquee":
      case "create": {
        const rect = viewport.getBoundingClientRect();
        const left = Math.min(gesture.from.x, event.clientX) - rect.left;
        const top = Math.min(gesture.from.y, event.clientY) - rect.top;
        Object.assign(marquee.style, { left: `${left}px`, top: `${top}px`, width: `${Math.abs(event.clientX - gesture.from.x)}px`, height: `${Math.abs(event.clientY - gesture.from.y)}px` });
        marquee.hidden = false;
        if (gesture.kind === "marquee") {
          const area = { x: Math.min(gesture.start.x, at.x), y: Math.min(gesture.start.y, at.y), w: Math.abs(at.x - gesture.start.x), h: Math.abs(at.y - gesture.start.y) };
          selected = new Set(gesture.keep);
          for (const item of board.items) {
            const box = Core.boxOf(item);
            if (box && item.kind !== "frame" && box.x < area.x + area.w && area.x < box.x + box.w && box.y < area.y + area.h && area.y < box.y + box.h) selected.add(item.id);
          }
          drawSelection();
        }
        break;
      }
      case "pen": {
        const [px, py] = gesture.points[gesture.points.length - 1];
        if (Math.hypot(at.x - px, at.y - py) * view.zoom < 3) return;
        gesture.points.push([Math.round(at.x), Math.round(at.y)]);
        drawMarks({ items: [...board.items, { id: "pen-drawing", kind: "pen", points: gesture.points }] });
        break;
      }
      case "arrow": {
        const end = { x: at.x, y: at.y };
        drawMarks({ items: [...board.items, { id: "arrow-drawing", kind: "arrow", from: gesture.from, to: end }] });
        break;
      }
    }
  });

  function endGesture(event) {
    if (!gesture) return;
    const done = gesture;
    gesture = null;
    marquee.hidden = true;
    viewport.classList.remove("panning");
    drawGuides([]);
    const at = toWorld(event);
    if (done.kind === "move" && done.moved) {
      send(Core.moveOps(board, done.ids, done.shift.dx, done.shift.dy));
    } else if (done.kind === "resize" && done.box) {
      send([{ op: "set", id: done.id, fields: done.box }]);
    } else if (done.kind === "pen" && done.points.length > 1) {
      send([{ op: "add", item: Core.newItem(board, "pen", 0, 0, { points: done.points }) }]);
    } else if (done.kind === "arrow") {
      const id = itemAt(event);
      const to = id ? { item: id } : { x: Math.round(at.x), y: Math.round(at.y) };
      const same = done.from.item && done.from.item === to.item;
      const far = Math.hypot(at.x - done.start.x, at.y - done.start.y) * view.zoom > 8;
      if (!same && far) send([{ op: "add", item: Core.newItem(board, "arrow", 0, 0, { from: done.from, to }) }]);
      else drawMarks();
    } else if (done.kind === "create") {
      const grid = board.settings?.grid || 20;
      const snap = (value) => Math.round(value / grid) * grid;
      const dragged = Math.abs(at.x - done.start.x) * view.zoom > 8 && Math.abs(at.y - done.start.y) * view.zoom > 8;
      const extra = dragged ? { w: snap(Math.abs(at.x - done.start.x)), h: snap(Math.abs(at.y - done.start.y)) } : {};
      const item = Core.newItem(board, done.tool, snap(Math.min(done.start.x, at.x)), snap(Math.min(done.start.y, at.y)), extra);
      selected = new Set([item.id]);
      send([{ op: "add", item }]);
      setTool("select");
      if (done.tool !== "highlight") startEdit(item.id);
    } else {
      drawMarks();
    }
    positionBar();
  }

  viewport.addEventListener("pointerup", endGesture);
  viewport.addEventListener("pointercancel", endGesture);

  viewport.addEventListener("dblclick", (event) => {
    const id = itemAt(event); // the item under the pointer: a captured pointer's events land on the canvas
    if (id) {
      selected = new Set([id]);
      startEdit(id);
    }
  });

  viewport.addEventListener("click", (event) => {
    const fill = event.target.closest('[data-act="fill"]');
    if (fill) vscode.postMessage({ type: "fill", id: fill.closest("[data-id]").getAttribute("data-id") });
  });

  viewport.addEventListener("wheel", (event) => {
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) {
      const rect = viewport.getBoundingClientRect();
      zoomAt(Math.exp(-event.deltaY * 0.0018), event.clientX - rect.left, event.clientY - rect.top);
    } else {
      view = { ...view, x: view.x - event.deltaX, y: view.y - event.deltaY };
      applyView();
    }
  }, { passive: false });

  const TOOLS = { v: "select", h: "hand", t: "note", l: "latex", f: "frame", s: "slot", p: "pen", a: "arrow", m: "highlight", c: "pin" };

  viewport.addEventListener("keydown", (event) => {
    if (editing) return;
    const ctrl = event.ctrlKey || event.metaKey;
    const key = event.key;
    if (key === " ") {
      spaceHeld = true;
      viewport.classList.add("tool-hand");
      event.preventDefault();
    } else if ((key === "Delete" || key === "Backspace") && selected.size) {
      removeSelected();
      event.preventDefault();
    } else if (key === "Escape") {
      selected = new Set();
      setTool("select");
      render();
    } else if (ctrl && key.toLowerCase() === "a") {
      selected = new Set(board.items.map((each) => each.id));
      render();
      event.preventDefault();
    } else if (ctrl && key.toLowerCase() === "d") {
      duplicate();
      event.preventDefault();
    } else if (ctrl && key.toLowerCase() === "g") {
      frameSelected();
      event.preventDefault();
    } else if (key.startsWith("Arrow") && selected.size) {
      const step = event.shiftKey ? board.settings?.grid || 20 : 1;
      const dx = key === "ArrowLeft" ? -step : key === "ArrowRight" ? step : 0;
      const dy = key === "ArrowUp" ? -step : key === "ArrowDown" ? step : 0;
      send(Core.moveOps(board, [...selected], dx, dy));
      event.preventDefault();
    } else if (!ctrl && key === "0") {
      fit();
    } else if (!ctrl && key === "1") {
      zoomAt(1 / view.zoom, viewport.clientWidth / 2, viewport.clientHeight / 2);
    } else if (!ctrl && (key === "+" || key === "=")) {
      zoomAt(1.25, viewport.clientWidth / 2, viewport.clientHeight / 2);
    } else if (!ctrl && key === "-") {
      zoomAt(0.8, viewport.clientWidth / 2, viewport.clientHeight / 2);
    } else if (!ctrl && !event.altKey && TOOLS[key.toLowerCase()]) {
      setTool(TOOLS[key.toLowerCase()]);
    }
  });

  viewport.addEventListener("keyup", (event) => {
    if (event.key === " ") {
      spaceHeld = false;
      viewport.classList.remove("tool-hand");
      setTool(tool);
    }
  });

  viewport.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });

  viewport.addEventListener("drop", (event) => {
    event.preventDefault();
    const at = toWorld(event);
    const list = event.dataTransfer?.getData("application/vnd.code.uri-list") || event.dataTransfer?.getData("text/uri-list") || "";
    const dropped = list.split(/\r?\n/).map((each) => each.trim()).filter((each) => each && !each.startsWith("#"));
    if (dropped.length) {
      vscode.postMessage({ type: "drop", uris: dropped, x: Math.round(at.x), y: Math.round(at.y) });
      return;
    }
    const file = [...(event.dataTransfer?.files || [])].find((each) => each.type.startsWith("image/"));
    if (file) readImage(file, at);
  });

  function readImage(file, at) {
    const reader = new FileReader();
    reader.onload = () => vscode.postMessage({
      type: "paste", mime: file.type, data: String(reader.result).split(",")[1] || "", x: Math.round(at.x), y: Math.round(at.y),
    });  // prettier-ignore
    reader.readAsDataURL(file);
  }

  function middle() {
    return { x: (viewport.clientWidth / 2 - view.x) / view.zoom, y: (viewport.clientHeight / 2 - view.y) / view.zoom };
  }

  document.addEventListener("paste", (event) => {
    if (editing || !askBox.hidden || !board) return;
    const image = [...(event.clipboardData?.items || [])].find((each) => each.type.startsWith("image/"));
    const file = image?.getAsFile();
    const at = middle();
    if (file) {
      event.preventDefault();
      readImage(file, at);
      return;
    }
    const text = event.clipboardData?.getData("text/plain");
    if (text?.trim()) {
      event.preventDefault();
      const latex = /^\s*(\$|\\\[|\\begin)/.test(text);
      const item = latex
        ? Core.newItem(board, "latex", Math.round(at.x), Math.round(at.y), { source: text.trim().replace(/^\$+|\$+$/g, "") })
        : Core.newItem(board, "note", Math.round(at.x), Math.round(at.y), { text });
      selected = new Set([item.id]);
      send([{ op: "add", item }]);
    }
  });

  // -- the toolbar, the selection's bar, the question

  for (const button of document.querySelectorAll(".tool[data-tool]")) {
    button.addEventListener("click", () => setTool(button.dataset.tool));
  }
  $("zoom-in").addEventListener("click", () => zoomAt(1.25, viewport.clientWidth / 2, viewport.clientHeight / 2));
  $("zoom-out").addEventListener("click", () => zoomAt(0.8, viewport.clientWidth / 2, viewport.clientHeight / 2));
  $("zoom-level").addEventListener("click", () => fit());
  $("send-pins").addEventListener("click", () => vscode.postMessage({ type: "pins" }));
  $("export").addEventListener("click", () => vscode.postMessage({ type: "export", ids: [...selected] }));
  for (const button of bar.querySelectorAll("[data-align]")) {
    button.addEventListener("click", () => send(Core.align(board, [...selected], button.dataset.align)));
  }
  bar.querySelector('[data-act="frame"]').addEventListener("click", frameSelected);
  bar.querySelector('[data-act="ask"]').addEventListener("click", openAsk);
  bar.querySelector('[data-act="delete"]').addEventListener("click", removeSelected);
  $("ask-send").addEventListener("click", sendAsk);
  $("ask-cancel").addEventListener("click", closeAsk);
  $("ask-text").addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendAsk();
    } else if (event.key === "Escape") {
      closeAsk();
    }
  });

  // -- what the extension sends

  window.addEventListener("message", (event) => {
    const message = event.data;
    if (message.type === "board") {
      board = message.board;
      path = message.path || path;
      uris = message.uris || {};
      compiled = message.compiled || compiled;
      said = message.said || "";
      selected = new Set([...selected].filter((id) => itemById(id)));
      render();
      if (!fitted && board.items.length) {
        fitted = true;
        fit();
      } else {
        applyView();
      }
    } else if (message.type === "theme") {
      document.body.className = message.theme && message.theme !== "vscode" ? `theme-${message.theme}` : "";
    } else if (message.type === "figure") {
      const image = new Image();
      image.onload = () => {
        const w = 360;
        const h = Math.round((w * image.naturalHeight) / Math.max(image.naturalWidth, 1));
        const item = Core.newItem(board, "figure", message.x, message.y, { file: message.file, w, h });
        selected = new Set([item.id]);
        send([{ op: "add", item }]);
      };
      image.src = message.uri;
    } else if (message.type === "select") {
      selected = new Set(message.ids || []);
      render();
      const chosen = (message.ids || []).map((id) => itemById(id)).filter(Boolean);
      if (chosen.length) fit(chosen);
    }
  });

  window.addEventListener("resize", () => positionBar());
  setTool("select");
  applyView();
  vscode.postMessage({ type: "ready" });
})();
