// Artifacts in VS Code (design 0021 §5): the service's `agents.artifact_made` read (`artifactMade`), and a page made
// ready to show (`artifactPage`): the agent's page as it wrote it, with Clank's content security policy first in its
// head (nothing from the network: the webview's own files, inline scripts and styles, and `eval`, which Plotly's and
// Mermaid's builds use), a <base> at its version's folder so its relative paths work, its `clank-lib/` names pointed
// at the extension's copy of the libraries (decision 0135), and Clank's bar at the end of its body. Pure:
// `artifacts.ts` beside `extension.ts` opens the panels and reads the files.

import type { ServerEvent } from "./events";

/** An artifact made, as its event says it. */
export interface ArtifactMade {
  workspace: string;
  folder: string;
  name: string;
  title: string;
  kind: string;
  version: number;
  entry: string;
}

/** Where a page's files and the libraries are, as the webview reaches them, and what goes into it. */
export interface PageParts {
  base: string; // the version's folder, ending with a slash
  lib: string; // the extension's copy of the libraries, no slash at the end
  source: string; // the webview's own source, for the policy
  nonce: string;
  bar: string; // Clank's bar: HTML, with its script carrying the nonce
}

/** The artifact an `agents.artifact_made` event names; nothing for any other event. */
export function artifactMade(message: ServerEvent): ArtifactMade | undefined {
  const data = (message.data as { data?: Partial<ArtifactMade> } | undefined)?.data;
  if (message.name !== "agents.artifact_made" || !data?.folder || !data.name || !data.entry) {
    return undefined;
  }
  return {
    workspace: String(data.workspace ?? ""), folder: data.folder, name: data.name, title: String(data.title ?? data.name),
    kind: String(data.kind ?? "html"), version: Number(data.version ?? 1), entry: data.entry,
  };
}

/** The page ready to show (module comment). */
export function artifactPage(page: string, parts: PageParts): string {
  const policy =
    `default-src 'none'; img-src ${parts.source} data: blob:; media-src ${parts.source} data: blob:; ` +
    `font-src ${parts.source} data:; style-src ${parts.source} 'unsafe-inline'; ` +
    `script-src ${parts.source} 'unsafe-inline' 'unsafe-eval'; connect-src ${parts.source};`;
  const head = `<meta http-equiv="Content-Security-Policy" content="${policy}"><base href="${parts.base}">`;
  let shown = page.replace(/(["'(])clank-lib\//g, `$1${parts.lib}/`);
  if (/<head[^>]*>/i.test(shown)) {
    shown = shown.replace(/<head[^>]*>/i, (open) => `${open}${head}`);
  } else if (/<html[^>]*>/i.test(shown)) {
    shown = shown.replace(/<html[^>]*>/i, (open) => `${open}<head>${head}</head>`);
  } else {
    shown = `<!doctype html><html><head>${head}</head><body>${shown}</body></html>`;
  }
  const close = shown.search(/<\/body>/i);
  return close >= 0 ? `${shown.slice(0, close)}${parts.bar}${shown.slice(close)}` : `${shown}${parts.bar}`;
}

/** Clank's bar over an artifact's page: its title, its versions, Comment and Open in browser, in a shadow root so its
 * styles and the page's never meet; it tells the extension what was chosen. */
export function artifactBar(title: string, versions: ReturnType<typeof versionsSaid>, nonce: string): string {
  const options = versions
    .map((each) => `<option value="${each.version}"${each.shown ? " selected" : ""}>${escaped(each.label)}</option>`)
    .join("");
  const inside =
    "<style>.bar{display:flex;gap:6px;align-items:center;font:12px system-ui,sans-serif;padding:4px 8px;" +
    "background:rgba(30,30,30,.86);color:#eee;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.4)}" +
    "button,select{font:inherit;color:inherit;background:rgba(255,255,255,.12);border:0;border-radius:4px;" +
    "padding:2px 6px;cursor:pointer}</style>" +
    `<div class="bar"><b>${escaped(title)}</b><select>${options}</select>` +
    '<button data-act="comment">Comment</button><button data-act="browser">Open in browser</button></div>';
  return (
    '<div id="clank-artifact-bar" style="position:fixed;top:8px;right:8px;z-index:2147483647"></div>' +
    `<template id="clank-artifact-bar-inside">${inside}</template>` + // inert until copied into the shadow root
    `<script nonce="${nonce}">(() => {` +
    "const vscode = acquireVsCodeApi();" +
    'const root = document.getElementById("clank-artifact-bar").attachShadow({ mode: "closed" });' +
    'root.appendChild(document.getElementById("clank-artifact-bar-inside").content.cloneNode(true));' +
    'root.querySelector("select").addEventListener("change", (event) =>' +
    ' vscode.postMessage({ type: "version", version: Number(event.target.value) }));' +
    'root.querySelectorAll("button").forEach((button) => button.addEventListener("click", () =>' +
    " vscode.postMessage({ type: button.dataset.act })));" +
    "})();</script>"
  );
}

function escaped(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** The versions as the bar lists them: the newest first, the one shown marked. */
export function versionsSaid(count: number, shown: number): Array<{ version: number; label: string; shown: boolean }> {
  const found = [];
  for (let version = count; version >= 1; version--) {
    found.push({ version, label: `version ${version}${version === count ? " (newest)" : ""}`, shown: version === shown });
  }
  return found;
}
