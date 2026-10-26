// The agent panel's page (design 0021 §4), direction A ("Quiet", the owner's choice, 2026-10-26): draws the blocks the
// extension sends (`core/conversation.ts` makes them; the extension adds each text's math set aside and each image's
// address), keeps the folds the owner opened or closed and the place they scrolled to, follows the theme the extension
// names, and sends back what the owner does: a message, a file named by @, an image pasted or picked, an answer to
// what waits, an artifact, an image or a job's log to open, older messages, and the header's actions. Nothing here
// reads the service. The conversation comes as the stream moves it (design 0023 §5): only the blocks whose content
// changed are drawn again (each kept by its id), the scroll stays at the bottom while the owner is there and a "new ↓"
// pill says when more came while they read above; a message of the owner's sent and not yet heard back shows as
// pending; Escape stops the agent while it works.
(function () {
  const vscode = acquireVsCodeApi();
  const main = document.getElementById("conversation");
  const list = document.getElementById("items");
  const older = document.getElementById("older");
  const input = document.getElementById("input");
  const files = document.getElementById("files");
  const send = document.getElementById("send");
  const pill = document.getElementById("new");
  const folds = {}; // what the owner opened (true) or closed (false), by item
  const rendered = new Map(); // each block drawn, by id: its content as JSON, and its element
  const chosen = {}; // a question's answers chosen so far, by question
  let state = "none";
  let found = []; // the files @ lists now
  let pick = 0;
  let asking = null; // the @ being typed: where it starts

  const SVG = "http://www.w3.org/2000/svg";
  const ICONS = {
    chevron: ["M6 4l4 4-4 4"],
    file: ["M4 1.5h5l3 3v10H4z", "M9 1.5v3h3"],
    edit: ["M10.5 2.5l3 3-8 8H2.5v-3z"],
    terminal: ["M1.5 4.5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2z", "M4.5 6l2 2-2 2M8.5 10.5h3"],
    search: ["M7 12.5a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11z", "M11 11l3.5 3.5"],
    folder: ["M1.5 4a1.5 1.5 0 0 1 1.5-1.5h3l1.5 2H13a1.5 1.5 0 0 1 1.5 1.5v6A1.5 1.5 0 0 1 13 13.5H3A1.5 1.5 0 0 1 1.5 12z"],
    globe: ["M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M1.5 8h13M8 1.5c2 2 2 11 0 13M8 1.5c-2 2-2 11 0 13"],
    list: ["M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.01M2.5 8h.01M2.5 12h.01"],
    agent: ["M8 7a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z", "M3 14c.5-2.8 2.5-4.5 5-4.5s4.5 1.7 5 4.5"],
    clock: ["M8 14a6 6 0 1 0 0-12 6 6 0 0 0 0 12z", "M8 4.5V8l2.5 1.5"],
    stop: ["M4.5 4.5h7v7h-7z"],
    sparkle: ["M8 1.5l1.6 4.9 4.9 1.6-4.9 1.6L8 14.5l-1.6-4.9L1.5 8l4.9-1.6z"],
    image: ["M3.5 2.5h9a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z", "M5.5 7.8a1.3 1.3 0 1 0 0-2.6 1.3 1.3 0 0 0 0 2.6z", "M14.5 11l-3.5-3.5L4 13.5"],
    eye: ["M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8s-2.5 4.5-6.5 4.5S1.5 8 1.5 8z", "M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"],
    tool: ["M10 2.5a3 3 0 0 0-3.6 3.8L2.5 10.2v3.3h3.3l3.9-3.9A3 3 0 0 0 13.5 6l-2 .5-2-2z"],
    board: ["M3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9A1.5 1.5 0 0 1 3.5 2z", "M2 6h12M6 6v8"],
    check: ["M3.5 8.5l3 3 6-7"],
    cross: ["M4.5 4.5l7 7M11.5 4.5l-7 7"],
    spinner: ["M8 1.5a6.5 6.5 0 1 0 6.5 6.5"],
    shield: ["M8 1.5l5.5 2v4c0 3.5-2.4 6-5.5 7-3.1-1-5.5-3.5-5.5-7v-4z"],
    send: ["M8 13V3M3.5 7.5L8 3l4.5 4.5"],
    halt: ["M5 5h6v6H5z"],
  };

  function icon(name, className) {
    const node = document.createElementNS(SVG, "svg");
    node.setAttribute("viewBox", "0 0 16 16");
    node.setAttribute("aria-hidden", "true");
    if (className) node.setAttribute("class", className);
    for (const d of ICONS[name] || ICONS.tool) {
      const path = document.createElementNS(SVG, "path");
      path.setAttribute("d", d);
      node.append(path);
    }
    return node;
  }

  const escaped = (text) =>
    String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  if (window.marked) {
    // the model's raw HTML is shown as text, never as markup
    window.marked.use({ renderer: { html: (token) => escaped(typeof token === "string" ? token : token.text) } });
  }

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value === undefined || value === null) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
    return node;
  }

  function duration(seconds) {
    if (seconds === null || seconds === undefined) return "";
    if (seconds < 60) return `${seconds} s`;
    const minutes = Math.floor(seconds / 60);
    return seconds % 60 ? `${minutes} min ${seconds % 60} s` : `${minutes} min`;
  }

  /** A text of the model's: its Markdown drawn, then each piece of math set aside drawn by KaTeX in its place. */
  function markdown(split) {
    const html = window.marked ? window.marked.parse(split.text) : escaped(split.text);
    return html.replace(/@@MATH(\d+)@@/g, (whole, index) => {
      const piece = split.math[Number(index)];
      if (!piece || !window.katex) return whole;
      return window.katex.renderToString(piece.text, { displayMode: piece.display, throwOnError: false });
    });
  }

  /** A fold: open as the owner left it, else as it opens by itself. */
  function fold(id, className, summary, body, open = false) {
    const details = el("details", { class: `item ${className}`, "data-id": id }, summary, body);
    details.open = folds[id] ?? open;
    summary.addEventListener("click", () => {
      folds[id] = !details.open; // the click opens or closes it after this
    });
    return details;
  }

  function thinking(item) {
    return fold(item.id, "thinking", el("summary", { class: "fold" }, icon("chevron", "chevron"), "Thinking"),
                el("div", { class: "thought", text: item.text }));  // prettier-ignore
  }

  function call(item) {
    const seconds = item.started && item.ended ? Math.round((item.ended - item.started) / 1000) : null;
    const status =
      item.status === "completed" ? icon("check", "ok")
      : item.status === "error" ? icon("cross", "failed")
      : icon("spinner", "spin");  // prettier-ignore
    const summary = el(
      "summary",
      { title: item.summary },
      el("span", { class: "kind" }, icon(item.view.icon)),
      el("span", { class: "verb", text: item.view.verb }),
      item.view.detail ? el("code", { class: "detail", text: item.view.detail }) : null,
      el("span", { class: "end" }, seconds ? el("span", { text: duration(seconds) }) : null, status),
    );
    const body = el(
      "div",
      { class: "body" },
      el("pre", { text: item.input }),
      item.output ? el("pre", { text: item.output }) : null,
      item.error ? el("pre", { class: "failed", text: item.error }) : null,
    );
    return fold(item.id, `call ${item.status}`, summary, body);
  }

  function steps(block) {
    const said = [`${block.calls} steps`, duration(block.seconds)].filter(Boolean).join(" · ");
    const summary = el("summary", { class: "fold" }, icon("chevron", "chevron"), said);
    return fold(block.id, "steps", summary, el("div", { class: "rail" }, ...block.steps.map(draw)), block.running);
  }

  function question(item) {
    const box = el("div", { class: "item ask", "data-id": item.id });
    item.questions.forEach((asked, index) => {
      box.append(el("div", { class: "ask-head" }, icon("shield"), asked.question || asked.header || "The agent asks"));
      const options = el("div", { class: "actions" });
      for (const option of asked.options || []) {
        options.append(
          el("button", {
            class: "secondary",
            text: option.label,
            title: option.description || "",
            onclick: () => {
              chosen[item.id] = chosen[item.id] || [];
              chosen[item.id][index] = [option.label];
              const answers = item.questions.map((_, each) => chosen[item.id][each]);
              if (answers.every(Boolean)) vscode.postMessage({ type: "question", id: item.id, answers });
            },
          }),
        );
      }
      box.append(options);
    });
    return box;
  }

  function draw(block) {
    switch (block.kind) {
      case "owner":
        return el("div", { class: block.pending ? "item owner pending" : "item owner", "data-id": block.id },
                  block.about ? el("span", { class: "about", text: block.about }) : null,
                  el("div", { class: "bubble", text: block.text }),
                  block.pending ? el("span", { class: "sending", text: "sending…" }) : null);  // prettier-ignore
      case "notice":
        return el(
          "div",
          { class: "item notice", "data-id": block.id },
          icon("clock"),
          el("span", {}, el("b", { text: block.title }), ` · ${block.detail}`),
          block.log ? el("button", { class: "link", text: "Log", onclick: () => vscode.postMessage({ type: "open", path: block.log }) }) : null,
        );
      case "text": {
        const box = el("div", { class: "item prose", "data-id": block.id });
        box.innerHTML = markdown(block.split);
        return box;
      }
      case "thinking":
        return thinking(block);
      case "call":
        return call(block);
      case "steps":
        return steps(block);
      case "image":
        return el("figure", { class: "item image", "data-id": block.id, style: "margin: 0" },
                  el("img", { src: block.src || "", alt: block.path, title: block.path,
                              onclick: () => vscode.postMessage({ type: "image", path: block.path }) }));  // prettier-ignore
      case "artifact":
        return el(
          "div",
          { class: "item card", "data-id": block.id },
          el("span", { class: "tile" }, icon("sparkle")),
          el("div", { class: "meta" }, el("b", { text: block.title }), el("span", { text: `Artifact · version ${block.version}` }),
             el("div", { class: "actions", style: "margin-top: 8px" },
                el("button", { class: "primary", text: "Open",
                               onclick: () => vscode.postMessage({ type: "artifact", name: block.name, title: block.title,
                                                                   version: block.version }) }))),  // prettier-ignore
        );
      case "error":
        return el("div", { class: "item error-row", "data-id": block.id }, icon("cross"), el("span", { text: block.text }));
      case "compaction":
        return el("div", { class: "item band", "data-id": block.id, text: "The conversation was compacted here" });
      case "permission":
        return el(
          "div",
          { class: "item ask", "data-id": block.id },
          el("div", { class: "ask-head" }, icon("shield"), `The agent asks to use ${block.permission}`),
          block.patterns.length ? el("code", { text: block.patterns.join("\n") }) : null,
          el("div", { class: "actions" },
             ...[["once", "Allow once", "primary"], ["always", "Always", "secondary"], ["reject", "Reject", "secondary"]].map(
               ([reply, label, kind]) => el("button", { class: kind, text: label,
                                                        onclick: () => vscode.postMessage({ type: "permission", id: block.id, reply }) }),
             )),  // prettier-ignore
        );
      case "question":
        return question(block);
      default:
        return null;
    }
  }

  function atBottom() {
    return main.scrollHeight - main.scrollTop - main.clientHeight < 48;
  }

  function showFoot(foot) {
    const box = document.getElementById("foot");
    box.hidden = !foot;
    if (!foot) return;
    document.getElementById("foot-dot").className = `dot small ${state}`;
    document.getElementById("speed").textContent = foot.speed || foot.model;
    document.getElementById("used").textContent = foot.used ? `${foot.used} / ${foot.window}` : "";
    document.getElementById("meter").style.width = `${Math.min(100, Math.round(foot.share * 100))}%`;
    document.getElementById("drafts").textContent = foot.drafts;
    document.getElementById("gpu").textContent = foot.gpu;
  }

  function showSend() {
    const working = state === "working";
    send.className = working ? "send stop" : "send";
    send.setAttribute("aria-label", working ? "Stop the agent" : "Send");
    send.title = working ? "Stop the agent" : "Send (Enter)";
    document.getElementById("send-icon").setAttribute("d", ICONS[working ? "halt" : "send"][0]);
  }

  function showFiles() {
    files.replaceChildren(
      ...found.map((path, index) =>
        el("div", { class: index === pick ? "chosen" : "", text: path, onclick: () => choose(index) }),
      ),
    );
    files.hidden = !found.length || asking === null;
  }

  function choose(index) {
    const path = found[index];
    if (path === undefined || asking === null) return;
    const before = input.value.slice(0, asking);
    const after = input.value.slice(input.selectionStart);
    input.value = `${before}/workspace/${path} ${after}`;
    input.selectionStart = input.selectionEnd = before.length + path.length + 12;
    asking = null;
    found = [];
    showFiles();
    input.focus();
  }

  function submit() {
    if (state === "working" && !input.value.trim()) {
      vscode.postMessage({ type: "act", act: "stop" });
      return;
    }
    const text = input.value.trim();
    if (text) vscode.postMessage({ type: "send", text });
  }

  window.addEventListener("message", (event) => {
    const message = event.data;
    if (message.type === "conversation") {
      const stay = atBottom();
      state = message.state || "none";
      document.getElementById("dot").className = `dot ${state}`;
      document.getElementById("title").textContent = message.title || "No session yet";
      document.getElementById("subtitle").textContent = message.subtitle || "";
      document.getElementById("model").textContent = message.model || "";
      older.hidden = !message.older;
      const next = new Map();
      const nodes = [];
      let changed = false;
      for (const block of message.blocks) {
        const json = JSON.stringify(block);
        const kept = rendered.get(block.id);
        const node = kept && kept.json === json ? kept.node : draw(block);
        if (!node) continue;
        if (!kept || kept.json !== json) changed = true;
        nodes.push(node);
        next.set(block.id, { json, node });
      }
      if (next.size !== rendered.size) changed = true;
      rendered.clear();
      for (const [id, entry] of next) rendered.set(id, entry);
      list.replaceChildren(...(nodes.length ? nodes : [el("div", { class: "empty", text: message.empty || "Write to the agent to start." })]));
      showFoot(message.foot);
      showSend();
      if (stay) main.scrollTop = main.scrollHeight;
      else if (changed) pill.hidden = false;
    } else if (message.type === "theme") {
      document.body.className = message.theme && message.theme !== "vscode" ? `theme-${message.theme}` : "";
    } else if (message.type === "files") {
      found = message.files;
      pick = 0;
      showFiles();
    } else if (message.type === "insert") {
      const at = input.selectionStart;
      input.value = `${input.value.slice(0, at)}${message.text}${input.value.slice(at)}`;
      input.focus();
    } else if (message.type === "sent") {
      input.value = "";
    }
  });

  input.addEventListener("input", () => {
    const typed = /@([\w./-]*)$/.exec(input.value.slice(0, input.selectionStart));
    asking = typed ? input.selectionStart - typed[0].length : null;
    if (typed) vscode.postMessage({ type: "files", query: typed[1] });
    else {
      found = [];
      showFiles();
    }
  });

  input.addEventListener("keydown", (event) => {
    if (!files.hidden && found.length) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        pick = (pick + (event.key === "ArrowDown" ? 1 : found.length - 1)) % found.length;
        showFiles();
        event.preventDefault();
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        choose(pick);
        event.preventDefault();
        return;
      }
      if (event.key === "Escape") {
        asking = null;
        showFiles();
        return;
      }
    }
    if (event.key === "Escape" && state === "working") {
      event.preventDefault();
      vscode.postMessage({ type: "act", act: "stop" });
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  });

  main.addEventListener("scroll", () => {
    if (atBottom()) pill.hidden = true;
  });
  pill.addEventListener("click", () => {
    main.scrollTop = main.scrollHeight;
    pill.hidden = true;
  });

  input.addEventListener("paste", (event) => {
    const image = [...(event.clipboardData?.items || [])].find((each) => each.type.startsWith("image/"));
    const file = image?.getAsFile();
    if (!file) return;
    event.preventDefault();
    const reader = new FileReader();
    reader.onload = () => {
      const data = String(reader.result).split(",")[1] || "";
      vscode.postMessage({ type: "paste", mime: file.type, data });
    };
    reader.readAsDataURL(file);
  });

  send.addEventListener("click", submit);
  document.getElementById("at").addEventListener("click", () => {
    const at = input.selectionStart;
    input.value = `${input.value.slice(0, at)}@${input.value.slice(at)}`;
    input.selectionStart = input.selectionEnd = at + 1;
    input.focus();
    input.dispatchEvent(new Event("input"));
  });
  document.getElementById("image").addEventListener("click", () => vscode.postMessage({ type: "pickImage" }));
  older.addEventListener("click", () => vscode.postMessage({ type: "older" }));
  document.querySelectorAll(".tools button").forEach((button) =>
    button.addEventListener("click", () => vscode.postMessage({ type: "act", act: button.dataset.act })),
  );
  vscode.postMessage({ type: "ready" });
})();
