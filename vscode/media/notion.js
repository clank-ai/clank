// The review of a batch of Notion changes (design 0010 §6), inside VS Code's webview. The extension sends the batch
// and the tables of its databases (`review`); the page shows one database at a time (a tab for each when there are
// several): its changed rows and their neighbors, or every row, each marked + new, ~ changed (what it was struck above
// what it would be) or − removed, with a checkbox; and under the table the entry chosen: its Fields (in Notion now,
// proposed, a checkbox each), its Page (block by block) and how it will look As in Notion. Everything not written yet is
// checked at first; what the owner unchecks stays staged when they approve the rest. A new entry is made with its title,
// so unchecking the title unchecks the rest and checking a part checks the title. What the owner checked, the database
// and the entry chosen and the view are kept with the page (VS Code's state), and kept when the batch is shown again
// after an approval. The owner comments on the batch, an entry, a property or a block of its page (each with its thread
// beneath it: the comment, whether it is sent, the agent's answer), takes back one not sent yet, and sends the batch
// back with them; a proposal revised for the comments says what changed since the last revision. The page only shows
// and asks: approving, rejecting, commenting, sending back and opening a link go to the extension.
(function () {
  "use strict";

  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);
  const SIGNS = { added: "+", changed: "~", removed: "−", same: "" };
  const STATUS = { added: "New", changed: "Changed", removed: "Removed", same: "No change" };
  const ACTIVE = new Set(["ready", "partly written"]);
  const COMMENTED = new Set(["ready", "partly written", "returned"]); // a batch the owner may still comment on
  const SHORT = 90; // the characters of an unchanged block shown where unchanged blocks are folded

  let review = null; // the batch, its tables, and whether every row is shown, as the extension sent them
  const saved = vscode.getState() || {};
  const state = {
    batch: saved.batch || null, // the batch the choices below are of
    revision: saved.revision || 0,
    database: saved.database || null,
    selected: saved.selected || null, // a proposal's id, or "row:" and an entry's id
    view: saved.view || "fields",
    checked: saved.checked || {}, // a proposal's id: the parts of it checked
    composing: saved.composing || null, // where a comment is being written: "batch", a proposal, ":field:", ":block:"
    draft: saved.draft || "",
  };

  function keep() {
    vscode.setState(state);
  }

  /** An element: its attributes (`text` its text, `on...` its listeners), then its children. */
  function el(tag, attributes, ...children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes || {})) {
      if (value === undefined || value === null || value === false) {
        continue;
      }
      if (name === "class") {
        node.className = value;
      } else if (name === "text") {
        node.textContent = value;
      } else if (name.startsWith("on")) {
        node.addEventListener(name.slice(2), value);
      } else {
        node.setAttribute(name, value === true ? "" : String(value));
      }
    }
    for (const child of children.flat()) {
      if (child !== null && child !== undefined && child !== false) {
        node.append(typeof child === "string" ? document.createTextNode(child) : child);
      }
    }
    return node;
  }

  /** Nodes to add, without the empty ones (`append` would write a null as text). */
  function nodes(...given) {
    return given.flat().filter((each) => each !== null && each !== undefined && each !== false && each !== "");
  }

  /** A proposal's parts, each approved on its own: its properties by name and its page, or its removal. */
  function parts(proposal) {
    if (proposal.kind === "removal") {
      return ["removal"];
    }
    const page = proposal.kind === "entry" ? (proposal.blocks || []).length || proposal.markdown : (proposal.changes || []).length;
    return proposal.fields.map((field) => field.name).concat(page ? ["page"] : []);
  }

  function written(proposal) {
    return (proposal.done && proposal.done.parts) || [];
  }

  function left(proposal) {
    const done = written(proposal);
    return parts(proposal).filter((part) => !done.includes(part));
  }

  /** A new entry not made yet: it is made with its title. */
  function unmade(proposal) {
    return proposal.kind === "entry" && !proposal.done;
  }

  function titleName(proposal) {
    const payload = proposal.payload || {};
    return Object.keys(payload).find((name) => payload[name] && "title" in payload[name]) || "";
  }

  function proposalOf(id) {
    return review.batch.proposals.find((proposal) => proposal.id === id) || null;
  }

  function checkedOf(proposal) {
    return state.checked[proposal.id] || [];
  }

  function active() {
    return ACTIVE.has(review.batch.state);
  }

  function commentable() {
    return COMMENTED.has(review.batch.state);
  }

  function commentsOf(test) {
    return (review.batch.comments || []).filter(test);
  }

  /** A proposal's page as the blocks a comment can be on (as the service counts them). */
  function entryBlocks(proposal) {
    return (proposal.markdown || "").split("\n\n").map((each) => each.trim()).filter(Boolean);
  }

  function icon() {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M4 5h16v11H9l-5 4z");
    svg.append(path);
    return svg;
  }

  /** The button that opens a comment's composer, with how many comments are there. */
  function commentButton(key, count, label) {
    if (!commentable()) {
      return count ? el("span", { class: "comment-button", title: label }, icon(), String(count)) : null;
    }
    return el("button", {
      class: "comment-button",
      type: "button",
      "aria-label": label,
      title: label,
      onclick: (event) => {
        event.stopPropagation();
        state.composing = key;
        state.draft = "";
        keep();
        render();
        const area = document.querySelector(".composer textarea");
        if (area) {
          area.focus();
        }
      },
    }, icon(), count ? String(count) : "");
  }

  function clock(at) {
    const moment = new Date(at);
    return Number.isNaN(moment.getTime()) ? "" : moment.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  /** Comments as bubbles: what was said, whether it is sent, and the answers. */
  function thread(list) {
    if (!list.length) {
      return null;
    }
    return el("div", { class: "thread" }, list.map((comment) => {
      const said = comment.state === "answered" ? "answered" : comment.sent ? "sent to the agent" : "not sent yet";
      const back = !comment.sent && commentable()
        ? el("button", { class: "take-back", type: "button", text: "Take back", onclick: (event) => {
            event.stopPropagation();
            vscode.postMessage({ type: "uncomment", batch: review.batch.id, comment: comment.id });
          } })
        : null;
      return el("div", { class: `bubble ${comment.state}`, "data-comment": comment.id },
        el("div", { class: "bubble-head" }, `You · ${clock(comment.at)} · ${comment.id}, ${said}`, back),
        el("div", { text: comment.text }),
        comment.replies.map((reply) => el("div", { class: "reply" },
          el("strong", { text: reply.by === "you" ? "You: " : "The agent: " }), reply.text)));
    }));
  }

  /** The composer of a comment, when one is being written there. */
  function composer(key, place, label) {
    if (state.composing !== key) {
      return null;
    }
    const area = el("textarea", { "aria-label": label, rows: 3 });
    area.value = state.draft;
    area.addEventListener("input", () => {
      state.draft = area.value;
      keep();
    });
    const close = () => {
      state.composing = null;
      state.draft = "";
      keep();
      render();
    };
    const add = () => {
      const text = area.value.trim();
      if (text) {
        vscode.postMessage({ type: "comment", batch: review.batch.id, ...place, text });
        close();
      }
    };
    area.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        add();
      }
    });
    return el("div", { class: "composer" },
      el("label", {}, label, area),
      el("div", { class: "actions" },
        el("button", { class: "primary", type: "button", text: "Add comment", onclick: add }),
        el("button", { class: "secondary", type: "button", text: "Cancel", onclick: close })));
  }

  /** What changed in a proposal since the last revision, when it was revised (or added) in this one. */
  function revised(proposal) {
    const revision = review.batch.revision;
    if (revision < 2 || proposal.revision !== revision) {
      return "";
    }
    if (!proposal.previous) {
      return `New in revision ${revision}.`;
    }
    const before = proposal.previous.fields || [];
    const changes = [];
    for (const field of proposal.fields) {
      const was = before.find((each) => each.name === field.name);
      if (!was) {
        changes.push(`${field.name} is changed now`);
      } else if (was.now !== field.now) {
        changes.push(`${field.name} was ${was.now || "(empty)"}`);
      }
    }
    for (const was of before) {
      if (!proposal.fields.some((field) => field.name === was.name)) {
        changes.push(`${was.name} is no longer changed`);
      }
    }
    if ((proposal.previous.markdown || "") !== (proposal.markdown || "")) {
      changes.push("its page changed");
    }
    return changes.length
      ? `Revised in revision ${revision}: ${changes.join("; ")}.`
      : `Proposed again in revision ${revision}, unchanged.`;
  }

  function rowKey(row) {
    return row.proposal || `row:${row.id}`;
  }

  /** A batch sent: the choices kept for it (dropping parts written since), or every part not written for a new one. */
  function adopt(next) {
    const batch = next.batch;
    const fresh = state.batch !== batch.id || state.revision !== batch.revision;
    const checked = {};
    for (const proposal of batch.proposals) {
      const open = left(proposal);
      const before = fresh ? undefined : state.checked[proposal.id];
      checked[proposal.id] = before === undefined ? open : before.filter((part) => open.includes(part));
    }
    Object.assign(state, { batch: batch.id, revision: batch.revision, checked });
    if (fresh) {
      Object.assign(state, { database: null, selected: null });
    }
    const select = next.select || {};
    if (select.database) {
      state.database = select.database;
    }
    if (select.proposal) {
      state.selected = select.proposal;
    }
    if (!next.tables.some((table) => table.database === state.database)) {
      state.database = next.tables.length ? next.tables[0].database : null;
    }
    const table = next.tables.find((each) => each.database === state.database);
    if (table && !table.rows.some((row) => rowKey(row) === state.selected)) {
      const first = table.rows.find((row) => row.proposal) || table.rows[0];
      state.selected = first ? rowKey(first) : null;
    }
    review = next;
    keep();
  }

  /** Check or uncheck a part of a proposal (`part` null: every part not written). */
  function toggle(proposal, part, on) {
    const open = left(proposal);
    const now = new Set(checkedOf(proposal));
    for (const each of part === null ? open : [part]) {
      if (on) {
        now.add(each);
      } else {
        now.delete(each);
      }
    }
    if (unmade(proposal)) {
      const title = titleName(proposal);
      if (part === title && !on) {
        now.clear(); // without its title the entry cannot be made
      } else if (on && title) {
        now.add(title);
      }
    }
    state.checked[proposal.id] = open.filter((each) => now.has(each));
    keep();
    render();
  }

  function select(key) {
    state.selected = key;
    keep();
    render();
  }

  function checkbox(label, on, change, disabled) {
    const box = el("input", { type: "checkbox", "aria-label": label, disabled: disabled || !active() });
    box.checked = on;
    box.addEventListener("click", (event) => event.stopPropagation());
    box.addEventListener("change", () => change(box.checked));
    return box;
  }

  function approve(chosen) {
    vscode.postMessage({ type: "approve", batch: review.batch.id, parts: chosen });
  }

  /** The parts checked of these proposals, by proposal (those with none left out). */
  function chosenOf(proposals) {
    const chosen = {};
    for (const proposal of proposals) {
      const checked = checkedOf(proposal).filter((part) => left(proposal).includes(part));
      if (checked.length) {
        chosen[proposal.id] = checked;
      }
    }
    return chosen;
  }

  function render() {
    if (!review) {
      return;
    }
    const batch = review.batch;
    const table = review.tables.find((each) => each.database === state.database);
    $("summary").textContent = batch.summary || `Batch ${batch.id}`;
    $("line").textContent = `${batch.id} · from the agent of ${batch.workspace} · revision ${batch.revision} · ${batch.state}`;
    banner(batch);
    tabs();
    batchComments();
    const unsent = commentsOf((comment) => !comment.sent).length;
    $("send-back").textContent = unsent === 1 ? "Send back with 1 comment" : `Send back with ${unsent} comments`;
    $("send-back").disabled = !unsent || !commentable();
    $("send-back").hidden = !commentable() && !unsent;
    $("near").setAttribute("aria-pressed", String(!review.everything));
    $("all").setAttribute("aria-pressed", String(review.everything));
    $("reject").disabled = !active();
    if (!table) {
      $("database").textContent = "No database";
      $("database-line").textContent = "This batch proposes nothing.";
      $("head").replaceChildren();
      $("rows").replaceChildren();
      $("detail").hidden = true;
      return;
    }
    const proposals = batch.proposals.filter((proposal) => proposal.database === table.database);
    const chosen = Object.keys(chosenOf(proposals)).length;
    $("approve").textContent = chosen === 1 ? "Approve 1 checked" : `Approve ${chosen} checked`;
    $("approve").disabled = !active() || !chosen;
    $("database").textContent = table.name;
    const unshared = table.shared ? "" : " · no longer shared with Clank's integration: only the proposals show";
    const changes = proposals.length === 1 ? "1 change proposed" : `${proposals.length} changes proposed`;
    $("database-line").textContent = `${changes} · click an entry to see its change${unshared}`;
    $("head").replaceChildren(el("th", { "aria-label": "Include" }), ...table.columns.map((column) => el("th", { text: column })));
    $("rows").replaceChildren(...table.rows.map((row) => rowView(row, table)));
    detail(table);
  }

  function banner(batch) {
    const waiting = batch.proposals.filter((proposal) => left(proposal).length).length;
    const said = {
      written: "Written to Notion: every proposal of this batch.",
      rejected: `Rejected${batch.reason ? `: ${batch.reason}` : ""}. Nothing of it is written.`,
      "partly written": `Partly written: ${waiting} of ${batch.proposals.length} proposals wait for you.`,
      returned: "Sent back to the agent with your comments: its next revision shows here.",
    }[batch.state];
    $("banner").hidden = !said;
    $("banner").textContent = said || "";
  }

  function batchComments() {
    const list = commentsOf((comment) => comment.proposal === null);
    const box = $("batch-comments");
    const open = state.composing === "batch";
    if (!list.length && !open && !commentable()) {
      box.replaceChildren();
      return;
    }
    box.replaceChildren(...nodes(
      list.length ? el("div", { class: "section-title", text: "Comments on the batch" }) : "",
      thread(list),
      composer("batch", {}, "Comment on the whole batch, for the agent"),
      open ? null : commentButton("batch", 0, "Comment on the batch"),
    ));
    const button = box.querySelector("button.comment-button");
    if (button) {
      button.append(" Comment on the batch");
    }
  }

  function tabs() {
    const nav = $("databases");
    nav.hidden = review.tables.length < 2;
    nav.replaceChildren(
      ...review.tables.map((table) => {
        const marked = table.rows.filter((row) => row.proposal).length;
        return el(
          "button",
          {
            type: "button",
            role: "tab",
            "aria-selected": String(table.database === state.database),
            onclick: () => {
              state.database = table.database;
              const first = table.rows.find((row) => row.proposal) || table.rows[0];
              state.selected = first ? rowKey(first) : null;
              keep();
              render();
            },
          },
          table.name,
          el("span", { class: "counts", text: marked === 1 ? "1 change" : `${marked} changes` }),
        );
      }),
    );
  }

  function rowView(row, table) {
    const proposal = row.proposal ? proposalOf(row.proposal) : null;
    const key = rowKey(row);
    const tr = el("tr", { class: `${row.mark}${key === state.selected ? " selected" : ""}`, "data-key": key, onclick: () => select(key) });
    const mark = el("td", { class: "mark" });
    if (proposal) {
      const open = left(proposal);
      if (!open.length) {
        mark.append(el("span", { class: "written", title: "Written to Notion", text: "✓" }));
      } else {
        const checked = checkedOf(proposal);
        const box = checkbox(`Include ${proposal.title}`, checked.length > 0, (on) => toggle(proposal, null, on));
        box.indeterminate = checked.length > 0 && checked.length < open.length;
        mark.append(box);
        if (proposal.result && proposal.result.error) {
          mark.append(el("span", { class: "failed", title: proposal.result.error, text: " !" }));
        }
      }
    }
    mark.append(el("span", { class: "sign", text: SIGNS[row.mark] }));
    const talk = proposal ? commentsOf((comment) => comment.proposal === proposal.id).length : 0;
    if (talk) {
      mark.append(el("span", { class: "comment-count", title: talk === 1 ? "1 comment" : `${talk} comments`, text: String(talk) }));
    }
    tr.append(mark);
    table.columns.forEach((column, index) => {
      const cell = row.cells[column] || { text: "" };
      const td = el("td", { class: index === 0 ? "cell-title" : "" });
      if (row.mark === "changed" && "was" in cell) {
        td.append(el("span", { class: "was", text: cell.was || "(empty)" }), el("span", { class: "now", text: cell.text || "(empty)" }));
      } else {
        td.textContent = cell.text;
      }
      tr.append(td);
    });
    return tr;
  }

  function detail(table) {
    const row = table.rows.find((each) => rowKey(each) === state.selected);
    $("detail").hidden = !row;
    if (!row) {
      return;
    }
    const proposal = row.proposal ? proposalOf(row.proposal) : null;
    $("crumb").textContent = `${table.name} › ${row.title}`;
    $("title").textContent = row.title;
    $("status").textContent = STATUS[row.mark];
    $("status").className = `status ${row.mark}`;
    for (const button of document.querySelectorAll("[data-view]")) {
      button.setAttribute("aria-selected", String(button.dataset.view === state.view));
    }
    const url = row.url || (proposal && ((proposal.done && proposal.done.url) || (proposal.result && proposal.result.url))) || "";
    $("open").hidden = !url;
    $("open").dataset.url = url;
    const open = proposal ? left(proposal) : [];
    $("approve-this").hidden = !proposal || !open.length || !active();
    $("approve-this").disabled = !proposal || !Object.keys(chosenOf([proposal])).length;
    why(proposal);
    result(proposal);
    const body = { fields: fieldsView, page: pageView, notion: notionView }[state.view] || fieldsView;
    $("body").replaceChildren(body(table, row, proposal));
    entryComments(proposal);
  }

  function entryComments(proposal) {
    const box = $("entry-comments");
    if (!proposal) {
      box.replaceChildren();
      return;
    }
    const list = commentsOf((comment) => comment.proposal === proposal.id && !comment.field && comment.block === null);
    const open = state.composing === proposal.id;
    const button = open ? null : commentButton(proposal.id, 0, "Comment on this entry");
    if (button && button.tagName === "BUTTON") {
      button.append(" Comment on this entry");
    }
    box.replaceChildren(...nodes(
      list.length || open || commentable() ? el("div", { class: "section-title", text: "Comments on the whole entry" }) : "",
      thread(list),
      composer(proposal.id, { proposal: proposal.id }, "Comment on this entry, for the agent"),
      button,
    ));
  }

  function why(proposal) {
    const box = $("why");
    const lines = [];
    if (proposal) {
      const change = revised(proposal);
      if (change) {
        lines.push(el("p", {}, el("strong", { text: change })));
      }
      lines.push(el("p", {}, el("strong", { text: "Why: " }), proposal.why));
      if (proposal.sources.length) {
        lines.push(el("p", {}, el("strong", { text: "Sources: " }), proposal.sources.join("; ")));
      }
      for (const note of proposal.notes) {
        lines.push(el("p", { text: note }));
      }
    }
    box.hidden = !lines.length;
    box.replaceChildren(...lines);
  }

  function result(proposal) {
    const box = $("result");
    const found = proposal && proposal.result;
    let said = "";
    if (found && found.error) {
      said = `Not written: ${found.error}`;
    } else if (found && found.written) {
      said = "Written to Notion.";
    } else if (found) {
      said = `Written in part (${written(proposal).join(", ")}); the rest waits for you.`;
    }
    box.hidden = !said;
    box.className = `result${found && found.error ? " failed" : ""}`;
    box.textContent = said;
  }

  function fieldsView(table, row, proposal) {
    const frame = el("div", { class: "table-frame" });
    const grid = el("table", { class: "fields" });
    grid.append(el("thead", {}, el("tr", {}, ["Field", "In Notion now", "Proposed", "Include", ""].map((name) => el("th", { text: name })))));
    const talk = (name) => {
      if (!proposal) {
        return [el("td", { class: "talk" })];
      }
      const key = `${proposal.id}:field:${name}`;
      const list = commentsOf((comment) => comment.proposal === proposal.id && comment.field === name);
      return [el("td", { class: "talk" }, commentButton(key, list.length, `Comment on ${name}`))];
    };
    const threadRows = (name) => {
      if (!proposal) {
        return [];
      }
      const key = `${proposal.id}:field:${name}`;
      const list = commentsOf((comment) => comment.proposal === proposal.id && comment.field === name);
      const shown = [thread(list), composer(key, { proposal: proposal.id, field: name }, `Comment on ${name}, for the agent`)].filter(Boolean);
      return shown.length ? [el("tr", { class: "thread-row" }, el("td", { colspan: 5 }, shown))] : [];
    };
    const body = el("tbody");
    if (proposal && proposal.kind === "removal") {
      body.append(
        el("tr", { class: "proposed gone" },
          el("td", { text: "The whole entry" }),
          el("td", { text: row.title }),
          el("td", { text: "moves to Notion's trash" }),
          el("td", { class: "include" }, include(proposal, "removal", `Remove ${row.title}`)),
          el("td", { class: "talk" })),
      );
    } else {
      const names = table.columns.concat((proposal ? proposal.fields : []).map((field) => field.name).filter((name) => !table.columns.includes(name)));
      for (const name of names) {
        const field = proposal && proposal.fields.find((each) => each.name === name);
        const now = (row.cells[name] || { text: "" }).text;
        if (field) {
          const was = field.was || (proposal.kind === "entry" ? "(new entry)" : "(empty)");
          body.append(
            el("tr", { class: "proposed" },
              el("td", { text: name }),
              el("td", { class: field.was ? "was-cell" : "muted", text: was }),
              el("td", { class: "now-cell", text: field.now || "(empty)" }),
              el("td", { class: "include" }, include(proposal, name, `Include ${name}`)),
              talk(name)),
            ...threadRows(name),
          );
        } else {
          body.append(
            el("tr", { class: "unchanged" },
              el("td", { text: name }),
              el("td", { text: now }),
              el("td", { text: now }),
              el("td", { class: "include muted", text: "—" }),
              talk(name)),
            ...threadRows(name),
          );
        }
      }
    }
    grid.append(body);
    frame.append(grid);
    if (!proposal) {
      return el("div", {}, el("p", { class: "empty", text: "No change is proposed for this entry: it is shown for context." }), frame);
    }
    return frame;
  }

  /** A part's checkbox, or that it is written. */
  function include(proposal, part, label) {
    if (written(proposal).includes(part)) {
      return el("span", { class: "written", title: "Written to Notion", text: "✓" });
    }
    return checkbox(label, checkedOf(proposal).includes(part), (on) => toggle(proposal, part, on));
  }

  function pageView(_table, row, proposal) {
    if (!proposal) {
      return el("p", { class: "empty", text: "No change is proposed for this entry: Open in Notion shows its page." });
    }
    if (proposal.kind === "removal") {
      return el("p", { class: "empty", text: `${row.title} and its page move to Notion's trash, where you can restore them.` });
    }
    if (!parts(proposal).includes("page")) {
      return el("p", { class: "empty", text: proposal.kind === "entry" ? "The new entry has no page." : "The page is not changed." });
    }
    const label = proposal.kind === "entry" ? "Include its page" : "Include the page's changes";
    const head = written(proposal).includes("page")
      ? el("div", { class: "page-include written", text: "✓ The page is written to Notion." })
      : el("label", { class: "page-include" }, include(proposal, "page", label), label);
    const blocks = el("div", { class: "blocks" });
    const line = (index, block, also) => {
      const key = `${proposal.id}:block:${index}`;
      const list = commentsOf((comment) => comment.proposal === proposal.id && comment.block !== null && also(comment.block));
      blocks.append(...nodes(
        el("div", { class: "block-line", "data-block": index }, block, commentButton(key, list.length, "Comment on this block")),
        thread(list),
        composer(key, { proposal: proposal.id, block: index }, "Comment on this block, for the agent"),
      ));
    };
    if (proposal.kind === "entry") {
      entryBlocks(proposal).forEach((each, index) => {
        line(index, el("div", { class: "block add", text: each }), (block) => block === index);
      });
    } else {
      const changes = proposal.changes || [];
      for (let index = 0; index < changes.length; index++) {
        const change = changes[index];
        if (change.op === "keep") {
          let end = index;
          while (end + 1 < changes.length && changes[end + 1].op === "keep") {
            end++;
          }
          const count = end - index + 1;
          const first = change.markdown.split("\n").find((line) => !/^(\$\$|```)/.test(line.trim())) || "";
          const shown = first.length > SHORT ? `${first.slice(0, SHORT)}…` : first;
          const start = index;
          line(start, el("div", { class: "block kept", text: count === 1 ? `⋯ ${shown}` : `⋯ ${shown} (and ${count - 1} more blocks, unchanged)` }),
            (block) => block >= start && block <= end);
          index = end;
        } else if (change.op === "update") {
          const at = index;
          line(at, el("div", { class: "block update" }, el("span", { class: "old", text: change.was || "" }), el("span", { class: "new", text: change.markdown })),
            (block) => block === at);
        } else {
          const at = index;
          line(at, el("div", { class: `block ${change.op}`, text: change.markdown }), (block) => block === at);
        }
      }
    }
    return el("div", {}, head, blocks);
  }

  function notionView(table, row, proposal) {
    const card = el("div", { class: "notion" });
    const titleColumn = table.columns[0];
    const value = (name) => {
      const field = proposal && proposal.kind !== "removal" && proposal.fields.find((each) => each.name === name);
      return field ? field.now : (row.cells[name] || { text: "" }).text;
    };
    card.append(el("h1", { text: value(titleColumn) || row.title }));
    const props = el("div", { class: "props" });
    for (const name of table.columns.slice(1)) {
      if (value(name)) {
        props.append(el("div", { class: "name", text: name }), el("div", { text: value(name) }));
      }
    }
    card.append(props);
    if (!proposal) {
      card.append(el("div", { class: "after", text: "No change is proposed: Open in Notion shows its page." }));
      return card;
    }
    if (proposal.kind === "removal") {
      card.append(el("div", { class: "after", text: `This entry will no longer be in ${table.name}; Notion keeps it in its trash.` }));
      return card;
    }
    const page = proposal.markdown || (proposal.base && proposal.base.markdown) || "";
    card.append(markdown(page));
    card.append(el("div", { class: "after", text: "How the entry will look once approved." }));
    return card;
  }

  const INLINE = /(\*\*[^*]+\*\*|~~[^~]+~~|`[^`]+`|\$[^$\n]+\$|!?\[[^\]]*\]\([^)\s]*\)|\*[^*\s][^*]*\*)/g;

  /** A line of inline Markdown, as elements (nothing is read as HTML). */
  function inline(text) {
    const made = [];
    let last = 0;
    for (const match of text.matchAll(INLINE)) {
      if (match.index > last) {
        made.push(text.slice(last, match.index));
      }
      const token = match[0];
      if (token.startsWith("**")) {
        made.push(el("strong", {}, inline(token.slice(2, -2))));
      } else if (token.startsWith("~~")) {
        made.push(el("s", { text: token.slice(2, -2) }));
      } else if (token.startsWith("`")) {
        made.push(el("code", { text: token.slice(1, -1) }));
      } else if (token.startsWith("$")) {
        made.push(el("span", { class: "md-math", text: token.slice(1, -1) }));
      } else if (token.startsWith("[") || token.startsWith("![")) {
        const label = token.slice(token.indexOf("[") + 1, token.indexOf("]("));
        made.push(el("span", { class: "md-link" }, inline(label)));
      } else {
        made.push(el("em", { text: token.slice(1, -1) }));
      }
      last = match.index + token.length;
    }
    if (last < text.length) {
      made.push(text.slice(last));
    }
    return made;
  }

  /** A page's Markdown (as the service writes it) as Notion would show it. */
  function markdown(text) {
    const page = el("div", { class: "md" });
    const lines = text.split("\n");
    let paragraph = [];
    const flush = () => {
      if (paragraph.length) {
        page.append(el("div", { class: "md-p" }, inline(paragraph.join("\n"))));
        paragraph = [];
      }
    };
    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      const indent = line.length - line.trimStart().length;
      const bare = line.trim();
      const fence = /^(\$\$|```)/.exec(bare);
      if (fence) {
        flush();
        const close = fence[1];
        const body = [];
        while (index + 1 < lines.length && lines[index + 1].trim() !== close) {
          body.push(lines[++index]);
        }
        index++;
        page.append(el("div", { class: close === "$$" ? "md-eq" : "md-code", text: body.join("\n") }));
        continue;
      }
      const heading = /^(#{1,3}) (.*)$/.exec(bare);
      const item = /^(- \[[ x]\] |- ▸ |- |\* |\d+\. )(.*)$/.exec(bare);
      if (!bare) {
        flush();
      } else if (heading) {
        flush();
        page.append(el("div", { class: `md-h${heading[1].length}` }, inline(heading[2])));
      } else if (bare === "---") {
        flush();
        page.append(el("hr", { class: "md-hr" }));
      } else if (bare.startsWith(">")) {
        flush();
        page.append(el("div", { class: "md-quote" }, inline(bare.replace(/^>\s?/, ""))));
      } else if (item) {
        flush();
        const marker = item[1].startsWith("- [x]") ? "☑ " : item[1].startsWith("- [ ]") ? "☐ " : item[1].startsWith("- ▸") ? "▸ " : /^\d/.test(item[1]) ? item[1] : "• ";
        const entry = el("div", { class: "md-li" }, marker, inline(item[2]));
        entry.style.marginLeft = `${indent * 8 + 4}px`; // the style sheet's rules alone: inline styles are not allowed
        page.append(entry);
      } else {
        paragraph.push(bare);
      }
    }
    flush();
    return page;
  }

  $("near").addEventListener("click", () => vscode.postMessage({ type: "rows", batch: review.batch.id, everything: false }));
  $("all").addEventListener("click", () => vscode.postMessage({ type: "rows", batch: review.batch.id, everything: true }));
  $("reject").addEventListener("click", () => vscode.postMessage({ type: "reject", batch: review.batch.id }));
  $("send-back").addEventListener("click", () => vscode.postMessage({ type: "sendBack", batch: review.batch.id }));
  $("approve").addEventListener("click", () => {
    const proposals = review.batch.proposals.filter((proposal) => proposal.database === state.database);
    approve(chosenOf(proposals));
  });
  $("approve-this").addEventListener("click", () => {
    const proposal = proposalOf(state.selected);
    if (proposal) {
      approve(chosenOf([proposal]));
    }
  });
  $("open").addEventListener("click", () => vscode.postMessage({ type: "open", url: $("open").dataset.url }));
  for (const button of document.querySelectorAll("[data-view]")) {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      keep();
      render();
    });
  }
  window.addEventListener("message", (event) => {
    if (event.data && event.data.type === "review") {
      adopt(event.data.review);
      render();
    }
  });
  vscode.postMessage({ type: "ready" });
})();
