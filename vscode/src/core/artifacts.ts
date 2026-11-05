// Artifacts in VS Code (design 0021 §5): the service's `agents.artifact_made` read (`artifactMade`), and the panel's own
// document (`artifactPanel`, decision 0165), written by Clank alone: Clank's bar, the one call to VS Code's API, and an
// `<iframe sandbox="allow-scripts">` holding the version's page. The service builds that page whole, the one an export
// writes (its files and Clank's libraries inside it), and it reaches the frame as its `srcdoc`, so no script, message
// or address carries it. In the frame the page has an origin of its own: it reaches neither the panel's document nor
// VS Code's API, and the panel listens to no message, so only the bar's clicks reach the extension. The frame takes the
// panel's content policy as well as the page's own, so the panel holds itself to the page's (`PANEL_POLICY`). Open in
// browser opens the version only once the owner answers VS Code's own question (`openInBrowser`, decision 0156). Pure:
// `artifacts.ts` beside `extension.ts` opens the panels and asks the service for the pages.

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

/** A version as the service answers it to be shown (`GET agents/artifacts/{workspace}/{name}/page`): its page whole,
 * with the artifact's title and how many versions it has. */
export interface ArtifactShown {
  name: string;
  title: string;
  kind: string;
  version: number;
  versions: number;
  html: string;
}

/** The panel's content policy: the one every version's page carries first (`EXPORT_POLICY` in agents/artifacts.py; a
 * test reads it there), since the frame holds the page to the panel's policy as well as its own. Nothing on the
 * network; the page's files and libraries are inside it (inline, data and blob); inline scripts (the page's and the
 * panel's: a nonce here would stop the page's) and `eval`, which Plotly's and Mermaid's builds use. */
export const PANEL_POLICY =
  "default-src 'none'; img-src data: blob:; media-src data: blob:; font-src data:; style-src 'unsafe-inline' data:; " +
  "script-src 'unsafe-inline' 'unsafe-eval' data:; connect-src data: blob:; form-action 'none'; base-uri 'none'";

/** The frame's sandbox: its scripts run, and nothing else is allowed. Without `allow-same-origin` it has an origin of its
 * own, out of reach of the panel's document and VS Code's API; it cannot move the window, open one, submit a form,
 * show a dialog or start a download. */
export const FRAME_SANDBOX = "allow-scripts";

/** The panel's own styles: the frame fills it, white beneath the page as in a browser; the bar floats over its corner
 * as a widget of the window's VS Code theme (the find widget's ground, edge and shadow, the secondary buttons), with
 * the dark theme's colors where none is given. */
const PANEL_STYLE =
  "html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden}" +
  "#clank-artifact-page{display:block;width:100%;height:100%;border:0;background:#fff}" +
  ".bar{position:fixed;top:8px;right:8px;z-index:1;display:flex;gap:6px;align-items:center;" +
  "font:12px var(--vscode-font-family,system-ui),sans-serif;padding:4px 6px 4px 10px;" +
  "background:var(--vscode-editorWidget-background,#252526);color:var(--vscode-editorWidget-foreground,#cccccc);" +
  "border:1px solid var(--vscode-widget-border,#454545);border-radius:8px;" +
  "box-shadow:0 2px 8px var(--vscode-widget-shadow,rgba(0,0,0,.36))}" +
  ".bar button,.bar select{font:inherit;color:var(--vscode-button-secondaryForeground,#cccccc);" +
  "background:var(--vscode-button-secondaryBackground,#313131);border:0;border-radius:4px;padding:3px 8px;" +
  "cursor:pointer}.bar button:hover{background:var(--vscode-button-secondaryHoverBackground,#3c3c3c)}" +
  ".bar button:focus-visible,.bar select:focus-visible{outline:1px solid var(--vscode-focusBorder,#0078d4);" +
  "outline-offset:1px}";

/** The panel's script, its only one: it tells the extension what was chosen on the bar, and listens to nothing. */
const PANEL_SCRIPT =
  "(() => {" +
  "const vscode = acquireVsCodeApi();" +
  'const bar = document.getElementById("clank-artifact-bar");' +
  'bar.querySelector("select").addEventListener("change", (event) =>' +
  ' vscode.postMessage({ type: "version", version: Number(event.target.value) }));' +
  'bar.querySelectorAll("button").forEach((button) => button.addEventListener("click", () =>' +
  " vscode.postMessage({ type: button.dataset.act })));" +
  "})();";

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

/** The panel's own document (module comment): its policy first, Clank's bar, the page in the sandboxed frame as its
 * `srcdoc` (its ampersands and quotes escaped, so the attribute holds the page whole and ends only where Clank ends it),
 * and the panel's script. */
export function artifactPanel(page: string, title: string, versions: ReturnType<typeof versionsSaid>): string {
  return (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
    `<meta http-equiv="Content-Security-Policy" content="${PANEL_POLICY}">` +
    `<title>${escaped(title)}</title><style>${PANEL_STYLE}</style></head><body>` +
    artifactBar(title, versions) +
    `<iframe id="clank-artifact-page" title="${escaped(title)}" sandbox="${FRAME_SANDBOX}" ` +
    `srcdoc="${page.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}"></iframe>` +
    `<script>${PANEL_SCRIPT}</script></body></html>`
  );
}

/** Clank's bar over an artifact's page: its title, its versions, Comment and Open in browser. It lies in the panel's
 * document, outside the page's frame, so the page can neither draw over it nor press it. */
export function artifactBar(title: string, versions: ReturnType<typeof versionsSaid>): string {
  const options = versions
    .map((each) => `<option value="${each.version}"${each.shown ? " selected" : ""}>${escaped(each.label)}</option>`)
    .join("");
  return (
    `<div id="clank-artifact-bar" class="bar" role="toolbar" aria-label="Artifact"><b>${escaped(title)}</b>` +
    `<select aria-label="Version">${options}</select>` +
    '<button data-act="comment">Comment</button><button data-act="browser">Open in browser</button></div>'
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

/** The answer that opens a version in the browser. */
export const OPEN_IN_BROWSER = "Open in browser";

/** What opening a version in the browser needs of VS Code and the service: the owner's answer to a question (VS Code's
 * own, outside the page), the version exported as one page (its file), and that file opened. */
export interface BrowserSteps {
  confirm(question: string, detail: string, button: string): Promise<string | undefined>;
  exported(): Promise<string>;
  open(file: string): Promise<unknown>;
}

/** A 'browser' message from an artifact's page: the owner is asked first, naming the artifact, since a message from the
 * page cannot be told from a click on the bar (decision 0156); only the answer Open in browser exports the version and
 * opens it. The file opened, or undefined when the owner said anything else. */
export async function openInBrowser(
  title: string,
  name: string,
  version: number,
  steps: BrowserSteps,
): Promise<string | undefined> {
  const answer = await steps.confirm(
    `Open the artifact "${title}" (${name}, version ${version}) in your browser?`,
    "It is exported as one page and opened in your default browser, outside VS Code. Its page was written by the agent.",
    OPEN_IN_BROWSER,
  );
  if (answer !== OPEN_IN_BROWSER) {
    return undefined;
  }
  const file = await steps.exported();
  await steps.open(file);
  return file;
}

/** How long after the owner answered a page's question no other is asked for it. */
export const QUIET_MS = 3_000;

/** The questions one artifact's panel asks: one at a time, and none for a moment after each answer, so a page that
 * sends its 'browser' message again and again cannot keep VS Code's question in front of the owner. */
export class BrowserQuestions {
  private asking = false;
  private quietUntil = 0;

  constructor(private readonly now: () => number = Date.now) {}

  /** `openInBrowser`, unless a question is open or was just answered: then nothing is asked and nothing opens. */
  async open(title: string, name: string, version: number, steps: BrowserSteps): Promise<string | undefined> {
    if (this.asking || this.now() < this.quietUntil) {
      return undefined;
    }
    this.asking = true;
    try {
      return await openInBrowser(title, name, version, steps);
    } finally {
      this.asking = false;
      this.quietUntil = this.now() + QUIET_MS;
    }
  }
}
