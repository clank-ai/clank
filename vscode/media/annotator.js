// Clank's figure annotator page (design 0008 §6), inside VS Code's webview: the figure, the tools to mark it, and the
// message box. Marks are kept in the image's own pixels (marks.js); the figure is fit to the window (Ctrl and the wheel
// zoom). A note is written in a bubble that opens beside the point clicked (its pin); a note's bubble is dragged
// anywhere on the figure without moving its pin, and a click on it edits it. Enter sends the marks, the message and the
// marked-up copy (the figure at its own size with the marks drawn on it) to the extension, which sends them to the
// workspace's agent through the service; Shift+Enter starts a new line. The extension sends the figure (again when its
// file changes), and how a send went.
(function () {
  "use strict";

  const vscode = acquireVsCodeApi();
  const { PALETTE, TOOLS, Marks, tooSmall, draw, drawBadge, noteLayout, hitNote, measurer } = window.ClankMarks;
  const KEYS = { p: "pen", b: "box", c: "circle", a: "arrow", t: "text", h: "highlight", s: "strike", i: "insert" };
  const NAMES = { pen: "drawing", box: "box", circle: "circle", arrow: "arrow", text: "note" };
  const MOVED = 3; // screen pixels: a press on a bubble that moves less is a click (it edits the note)
  const marks = new Marks();
  const state = { tool: "pen", color: PALETTE[0], image: null, width: 0, height: 0, scale: 1, fit: true };
  let drawing = null;
  let sending = false;
  let note = null; // the note being written: its editor, its pin, its color, and the note it edits (if any)
  let moving = null; // a note's bubble being dragged: the note, where the press was, its bubble then, where it is now

  const $ = (id) => document.getElementById(id);
  const stage = $("stage");
  const canvas = $("canvas");
  const context = canvas.getContext("2d");
  const measure = measurer(document.createElement("canvas").getContext("2d"));
  const message = $("message");
  const status = $("status");

  for (const button of document.querySelectorAll("[data-tool]")) {
    button.addEventListener("click", () => choose(button.dataset.tool));
  }
  for (const color of PALETTE) {
    const swatch = document.createElement("button");
    swatch.className = "swatch";
    swatch.dataset.color = color;
    swatch.style.background = color;
    swatch.style.setProperty("--swatch", color);
    swatch.title = "Color of the next mark";
    swatch.setAttribute("aria-label", `Color ${color}`);
    swatch.addEventListener("click", () => {
      state.color = color;
      paintButtons();
    });
    $("colors").appendChild(swatch);
  }
  $("undo").addEventListener("click", () => marks.undo() && render());
  $("redo").addEventListener("click", () => marks.redo() && render());
  $("clear").addEventListener("click", () => {
    marks.clear();
    render();
  });
  $("fit").addEventListener("click", () => {
    state.fit = true;
    layout();
  });
  $("send").addEventListener("click", submit);

  function choose(tool) {
    if (!TOOLS.includes(tool)) return;
    state.tool = tool;
    document.body.dataset.tool = tool;
    paintButtons();
  }

  function paintButtons() {
    for (const button of document.querySelectorAll("[data-tool]")) {
      button.setAttribute("aria-pressed", String(button.dataset.tool === state.tool));
    }
    for (const swatch of document.querySelectorAll(".swatch")) {
      swatch.setAttribute("aria-pressed", String(swatch.dataset.color === state.color));
    }
    $("undo").disabled = !marks.past.length;
    $("redo").disabled = !marks.future.length;
    $("clear").disabled = !marks.count;
  }

  /** The figure fit to the stage (or at the zoom chosen), the canvas sized to it. */
  function layout() {
    if (!state.image) return;
    if (state.fit) {
      const room = [stage.clientWidth - 32, stage.clientHeight - 32];
      state.scale = Math.max(0.05, Math.min(room[0] / state.width, room[1] / state.height, 2));
    }
    const ratio = window.devicePixelRatio || 1;
    const shown = [Math.round(state.width * state.scale), Math.round(state.height * state.scale)];
    canvas.width = Math.round(shown[0] * ratio);
    canvas.height = Math.round(shown[1] * ratio);
    canvas.style.width = `${shown[0]}px`;
    canvas.style.height = `${shown[1]}px`;
    canvas.style.display = "block";
    $("empty").style.display = "none";
    render();
  }

  function render() {
    if (!state.image) return;
    const ratio = window.devicePixelRatio || 1;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(state.image, 0, 0, state.width * state.scale, state.height * state.scale);
    for (const mark of marks.list) {
      if (note && note.n === mark.n) drawBadge(context, mark, state.scale, state.width); // its editor shows the bubble
      else if (moving && moving.n === mark.n && moving.to) draw(context, { ...mark, bubble: moving.to }, ...sizes());
      else draw(context, mark, ...sizes());
    }
    if (drawing) draw(context, { ...drawing, n: marks.count + 1 }, ...sizes());
    if (note && note.n === undefined) drawBadge(context, { kind: "text", color: note.color, points: [note.at], n: marks.count + 1 }, state.scale, state.width);
    if (note) placeEditor();
    chips();
    paintButtons();
  }

  /** What drawing a mark on the screen takes after the mark: the scale shown, the image's width and height. */
  function sizes() {
    return [state.scale, state.width, state.height];
  }

  function chips() {
    const box = $("chips");
    box.replaceChildren(
      ...marks.list.map((mark) => {
        const chip = document.createElement("span");
        chip.className = "chip";
        const number = document.createElement("b");
        number.textContent = String(mark.n);
        number.style.background = mark.color;
        const words = document.createElement("span");
        words.textContent = mark.kind === "text" ? `note “${mark.text}”` : NAMES[mark.kind];
        if (mark.kind === "text") chip.title = mark.text;
        chip.append(number, words);
        return chip;
      }),
    );
  }

  /** A pointer's place in the image's pixels, kept inside the image. */
  function point(event) {
    const box = canvas.getBoundingClientRect();
    const x = (event.clientX - box.left) / state.scale;
    const y = (event.clientY - box.top) / state.scale;
    return [Math.max(0, Math.min(state.width, x)), Math.max(0, Math.min(state.height, y))];
  }

  canvas.addEventListener("pointerdown", (event) => {
    if (!state.image || event.button !== 0) return;
    event.preventDefault();
    const at = point(event);
    const hit = hitNote(marks.list, at, measure, state.width, state.height);
    if (hit) {
      const [left, top] = noteLayout(hit, measure, state.width, state.height).box;
      moving = { n: hit.n, from: at, bubble: [left, top], to: null };
      canvas.setPointerCapture(event.pointerId);
      return;
    }
    if (state.tool === "text" || state.tool === "insert") {
      openNote(at, undefined, state.tool);
      return;
    }
    drawing = { kind: state.tool, color: state.color, points: state.tool === "pen" ? [at] : [at, at] };
    canvas.setPointerCapture(event.pointerId);
    render();
  });

  canvas.addEventListener("pointermove", (event) => {
    if (moving) {
      const at = point(event);
      const [dx, dy] = [at[0] - moving.from[0], at[1] - moving.from[1]];
      if (moving.to || Math.hypot(dx, dy) * state.scale >= MOVED) {
        moving.to = [moving.bubble[0] + dx, moving.bubble[1] + dy];
        render();
      }
      return;
    }
    if (!drawing) {
      const over = state.image && hitNote(marks.list, point(event), measure, state.width, state.height);
      canvas.classList.toggle("over-note", Boolean(over));
      return;
    }
    const at = point(event);
    if (drawing.kind === "pen") {
      const last = drawing.points[drawing.points.length - 1];
      if (Math.hypot(at[0] - last[0], at[1] - last[1]) * state.scale >= 2) drawing.points.push(at);
    } else {
      drawing.points[1] = at;
    }
    render();
  });

  function finish() {
    if (moving) {
      const { n, to } = moving;
      moving = null;
      const mark = marks.list.find((each) => each.n === n);
      if (!mark) return;
      if (to) {
        const [left, top] = noteLayout({ ...mark, bubble: to }, measure, state.width, state.height).box;
        marks.moveNote(n, [left, top]); // kept where it shows: on the figure
        render();
      } else {
        openNote(mark.points[0], mark);
      }
      return;
    }
    if (!drawing) return;
    const done = drawing;
    drawing = null;
    if (!tooSmall(done, 6 / state.scale) && !(done.kind === "pen" && done.points.length < 2)) {
      marks.add(done.kind, done.color, done.points);
    }
    render();
  }
  canvas.addEventListener("pointerup", finish);
  canvas.addEventListener("pointercancel", finish);

  /** A note written in a bubble beside its pin (a new one at `at`, or the note `editing`): Enter keeps it,
   * Shift+Enter starts a new line, Escape (or leaving a new one empty) drops it; a click elsewhere keeps it. */
  function openNote(at, editing, kind) {
    closeNote(true);
    const editor = document.createElement("div");
    editor.className = "note-editor";
    const input = document.createElement("textarea");
    input.rows = 1;
    const inserting = (editing ? editing.kind : kind) === "insert";
    input.placeholder = inserting ? "What to insert here" : "Your note";
    input.value = editing ? editing.text : "";
    input.setAttribute("aria-label", "Note");
    const hint = document.createElement("div");
    hint.className = "note-hint";
    hint.textContent = "Enter keeps · Shift+Enter new line · Esc cancels";
    editor.append(input, hint);
    const color = editing ? editing.color : state.color;
    editor.style.setProperty("--note", color);
    note = {
      editor, input, at, color, kind: inserting ? "insert" : "text",
      n: editing ? editing.n : undefined, bubble: editing ? editing.bubble : undefined,
    };
    input.addEventListener("input", placeEditor);
    input.addEventListener("keydown", (key) => {
      if (key.key === "Enter" && !key.shiftKey && !key.isComposing) {
        key.preventDefault();
        closeNote(true);
      } else if (key.key === "Escape") {
        key.preventDefault();
        closeNote(false);
      }
    });
    input.addEventListener("blur", () => closeNote(true));
    stage.appendChild(editor);
    render();
    setTimeout(() => input.focus(), 0);
  }

  /** The note's editor where its bubble will be, as wide as the bubble's lines may be, growing with its words; kept
   * inside the figure as shown. */
  function placeEditor() {
    if (!note) return;
    const { editor, input } = note;
    const words = input.value || input.placeholder;
    const shape = noteLayout({ points: [note.at], text: words, bubble: note.bubble }, measure, state.width, state.height);
    const scale = state.scale;
    editor.style.font = `500 ${shape.size * scale}px sans-serif`;
    editor.style.padding = `${shape.padding * scale}px`;
    editor.style.borderRadius = `${shape.size * 0.5 * scale}px`;
    input.style.lineHeight = `${shape.line * scale}px`;
    input.style.width = `${shape.widest * scale}px`; // as wide as a note's lines may be: the kept bubble fits its words
    input.style.height = "auto";
    input.style.height = `${input.scrollHeight}px`;
    const figure = canvas.getBoundingClientRect();
    const room = stage.getBoundingClientRect();
    const [width, height] = [editor.offsetWidth, editor.offsetHeight];
    const left = Math.max(figure.left, Math.min(figure.left + shape.box[0] * scale, figure.right - width));
    const top = Math.max(figure.top, Math.min(figure.top + shape.box[1] * scale, figure.bottom - height));
    editor.style.left = `${left - room.left + stage.scrollLeft}px`;
    editor.style.top = `${top - room.top + stage.scrollTop}px`;
  }

  function closeNote(keep) {
    if (!note) return;
    const { editor, input, at, color, n, kind } = note;
    note = null;
    const text = input.value.trim();
    editor.remove();
    if (n === undefined) {
      if (keep && text) marks.add(kind, color, [at], text);
    } else if (keep && text !== marks.list.find((mark) => mark.n === n)?.text) {
      marks.editNote(n, text);
    }
    render();
  }

  document.addEventListener("keydown", (event) => {
    const typing = event.target === message || (note && event.target === note.input);
    if ((event.ctrlKey || event.metaKey) && !typing) {
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) {
        event.preventDefault();
        if (marks.undo()) render();
      } else if (key === "y" || (key === "z" && event.shiftKey)) {
        event.preventDefault();
        if (marks.redo()) render();
      }
      return;
    }
    if (!typing && !event.altKey && KEYS[event.key.toLowerCase()]) choose(KEYS[event.key.toLowerCase()]);
  });

  stage.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey || !state.image) return;
      event.preventDefault();
      state.fit = false;
      state.scale = Math.max(0.05, Math.min(8, state.scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
      layout();
    },
    { passive: false },
  );
  // The figure stays fit while its room changes: the window, or the composer growing (a chip, a longer message).
  new ResizeObserver(() => state.fit && layout()).observe(stage);

  message.addEventListener("input", grow);
  message.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submit();
    }
  });

  function grow() {
    message.style.height = "auto";
    message.style.height = `${message.scrollHeight}px`;
  }

  function say(text, kind) {
    status.textContent = text;
    status.dataset.kind = kind || "";
  }

  /** The figure at its own size with the marks drawn on it, as a PNG data URL. */
  function markedUp() {
    const copy = document.createElement("canvas");
    copy.width = state.width;
    copy.height = state.height;
    const paint = copy.getContext("2d");
    paint.drawImage(state.image, 0, 0);
    for (const mark of marks.list) draw(paint, mark, 1, state.width, state.height);
    return copy.toDataURL("image/png");
  }

  function submit() {
    if (sending || !state.image) return;
    const words = message.value.trim();
    if (!marks.count && !words) {
      say("Mark something on the figure, or write what to do.", "error");
      return;
    }
    sending = true;
    $("send").disabled = true;
    say("Sending to the agent…");
    vscode.postMessage({ type: "send", marks: marks.toJSON(), message: words, image: markedUp() });
  }

  window.addEventListener("message", (event) => {
    const data = event.data || {};
    if (data.type === "figure") {
      const image = new Image();
      image.onload = () => {
        state.image = image;
        state.width = image.naturalWidth;
        state.height = image.naturalHeight;
        $("name").textContent = data.name || "";
        document.body.dataset.page = data.page ? "true" : "false"; // a PDF's page: its tools for text show
        layout();
        if (data.updated) say("The figure changed on disk: this is the new version.");
      };
      image.src = data.src;
    } else if (data.type === "sent") {
      sending = false;
      $("send").disabled = false;
      marks.reset();
      message.value = "";
      grow();
      render();
      say(data.text, "sent");
    } else if (data.type === "failed") {
      sending = false;
      $("send").disabled = false;
      say(data.text, "error");
    }
  });

  choose("pen");
  vscode.postMessage({ type: "ready" });
})();
