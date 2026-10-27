// The readout's page (design 0021 §3): draws the rows the extension sends (`core/readout.ts` makes them), in the theme
// the extension names (the window's VS Code theme, or Clank Night: media/tokens.css), and says when it is ready for
// them. Each part of the context bar is colored by its kind, as the console colors it. Nothing here reads the service.
(function () {
  const vscode = acquireVsCodeApi();
  const text = (id, value) => {
    document.getElementById(id).textContent = value || "";
  };

  function tokens(count) {
    if (count >= 10000) return `${Math.round(count / 1000)}K`;
    return count >= 1000 ? `${(count / 1000).toFixed(1)}K` : String(count);
  }

  function bar(segments) {
    const box = document.getElementById("bar");
    const legend = document.getElementById("legend");
    box.replaceChildren();
    legend.replaceChildren();
    segments.forEach((segment, index) => {
      const kind = /^[a-z]+$/.test(segment.part || "") ? `part-${segment.part}` : `part${index % 6}`;
      const piece = document.createElement("span");
      piece.className = `piece ${kind}`;
      piece.style.width = `${Math.max(segment.share * 100, 0)}%`;
      piece.title = `${segment.label}: ${tokens(segment.tokens)}`;
      box.append(piece);
      const key = document.createElement("span");
      key.className = "key";
      const swatch = document.createElement("span");
      swatch.className = `swatch ${kind}`;
      key.append(swatch, `${segment.label} ${tokens(segment.tokens)}`);
      legend.append(key);
    });
  }

  window.addEventListener("message", (event) => {
    const message = event.data;
    if (message.type === "theme") {
      document.body.className = message.theme && message.theme !== "vscode" ? `theme-${message.theme}` : "";
      return;
    }
    if (message.type !== "rows") return;
    const rows = message.rows;
    text("title", rows.title);
    text("speed", rows.speed);
    text("graph", rows.graph);
    text("now", rows.now);
    text("context", rows.context);
    text("exact", rows.exact);
    text("engine", rows.engine);
    text("machine", rows.machine);
    text("jobs", rows.jobs);
    bar(rows.bar);
  });
  vscode.postMessage({ type: "ready" });
})();
