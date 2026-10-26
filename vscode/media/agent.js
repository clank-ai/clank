// The agent panel's page (design 0021 §4): draws the conversation the extension sends (`core/conversation.ts` makes
// its items; the extension adds each text's math set aside and each image's address), keeps the folds the owner opened
// and the place they scrolled to, and sends back what the owner does: a message, a file named by @, an image pasted,
// an answer to what waits, an artifact or an image to open, older messages, and the header's actions. Nothing here
// reads the service.
(function () {
  const vscode = acquireVsCodeApi();
  const main = document.getElementById("conversation");
  const list = document.getElementById("items");
  const older = document.getElementById("older");
  const input = document.getElementById("input");
  const files = document.getElementById("files");
  const opened = new Set(); // the folds the owner opened, by item
  const chosen = {}; // a question's answers chosen so far, by question
  let found = []; // the files @ lists now
  let pick = 0;
  let asking = null; // the @ being typed: where it starts

  const escaped = (text) =>
    String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  if (window.marked) {
    // the model's raw HTML is shown as text, never as markup
    window.marked.use({ renderer: { html: (token) => escaped(typeof token === "string" ? token : token.text) } });
  }

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    node.append(...children.filter((child) => child !== null && child !== undefined));
    return node;
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

  function fold(item, label, body, className) {
    const details = el("details", { class: `item ${className}`, "data-id": item.id }, el("summary", { text: label }), body);
    details.open = opened.has(item.id);
    details.addEventListener("toggle", () => (details.open ? opened.add(item.id) : opened.delete(item.id)));
    return details;
  }

  const GLYPHS = { completed: "✓", error: "✗", running: "…", pending: "…" };

  function questionItem(item) {
    const box = el("div", { class: "item wait", "data-id": item.id });
    item.questions.forEach((question, index) => {
      const row = el("div", {}, el("div", { text: question.question || question.header || "The agent asks" }));
      for (const option of question.options || []) {
        row.append(
          el("button", {
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
      box.append(row);
    });
    return box;
  }

  function draw(item) {
    switch (item.kind) {
      case "owner":
        return el("div", { class: "item owner", "data-id": item.id, text: item.text });
      case "text": {
        const box = el("div", { class: "item text", "data-id": item.id });
        box.innerHTML = markdown(item.split);
        return box;
      }
      case "thinking":
        return fold(item, "Thinking", el("div", { class: "body", text: item.text }), "thinking");
      case "call":
        return fold(
          item,
          `${GLYPHS[item.status] || "·"} ${item.summary}`,
          el("div", {}, el("pre", { text: item.input }), item.output ? el("pre", { text: item.output }) : null,
             item.error ? el("pre", { class: "error", text: item.error }) : null),  // prettier-ignore
          `call ${item.status}`,
        );
      case "image":
        return el(
          "div",
          { class: "item image", "data-id": item.id },
          el("img", { src: item.src || "", alt: item.path, title: item.path,
                      onclick: () => vscode.postMessage({ type: "image", path: item.path }) }),  // prettier-ignore
        );
      case "artifact":
        return el(
          "div",
          { class: "item card", "data-id": item.id },
          el("b", { text: item.title }),
          el("span", { class: "state", text: `artifact ${item.name}, version ${item.version}` }),
          el("button", { class: "primary", text: "Open",
                         onclick: () => vscode.postMessage({ type: "artifact", name: item.name, title: item.title,
                                                             version: item.version }) }),  // prettier-ignore
        );
      case "error":
        return el("div", { class: "item error", "data-id": item.id, text: item.text });
      case "compaction":
        return el("div", { class: "item band", "data-id": item.id, text: "The conversation was compacted here" });
      case "permission":
        return el(
          "div",
          { class: "item wait", "data-id": item.id },
          el("span", { text: `The agent asks to use ${item.permission}${item.patterns.length ? `: ${item.patterns.join(", ")}` : ""}` }),
          ...[["once", "Allow once"], ["always", "Always"], ["reject", "Reject"]].map(([reply, label]) =>
            el("button", { class: reply === "once" ? "primary" : "", text: label,
                           onclick: () => vscode.postMessage({ type: "permission", id: item.id, reply }) }),  // prettier-ignore
          ),
        );
      case "question":
        return questionItem(item);
      default:
        return null;
    }
  }

  function atBottom() {
    return main.scrollHeight - main.scrollTop - main.clientHeight < 40;
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

  function send() {
    const text = input.value.trim();
    if (!text) return;
    vscode.postMessage({ type: "send", text });
  }

  window.addEventListener("message", (event) => {
    const message = event.data;
    if (message.type === "conversation") {
      const stay = atBottom();
      document.getElementById("title").textContent = message.title || "No session yet";
      const state = document.getElementById("state");
      state.textContent = message.state || "";
      state.className = message.busy ? "state busy" : "state";
      older.hidden = !message.older;
      list.replaceChildren(...message.items.map(draw).filter(Boolean));
      if (stay) main.scrollTop = main.scrollHeight;
    } else if (message.type === "older") {
      const height = main.scrollHeight;
      list.prepend(...message.items.map(draw).filter(Boolean));
      older.hidden = !message.more;
      main.scrollTop += main.scrollHeight - height;
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
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
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

  document.getElementById("send").addEventListener("click", send);
  older.addEventListener("click", () => vscode.postMessage({ type: "older" }));
  document.querySelectorAll("header button").forEach((button) =>
    button.addEventListener("click", () => vscode.postMessage({ type: "act", act: button.dataset.act })),
  );
  vscode.postMessage({ type: "ready" });
})();
