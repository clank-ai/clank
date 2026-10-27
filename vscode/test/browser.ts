// Headless Edge for the tests of the extension's pages (the annotator, the Notion review): a page opened from a file and
// spoken to through the browser's debugging protocol (evaluate, wait until, mouse, click), with the page as VS Code's
// webview shows it (`webviewPage`: its template filled in, and a stand-in for VS Code's API that keeps what the page
// posts in `window.posted`). `EDGE` is undefined where no Edge is installed (the Linux runs): the tests skip there.

import assert from "node:assert/strict";
import { type ChildProcess, spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import * as path from "node:path";
import { pathToFileURL } from "node:url";

export const EDGE = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find((candidate) => existsSync(candidate));
export const MEDIA = path.join(__dirname, "..", "..", "media");

/** A test's folder removed once its Edge is closed. On a busy Windows machine Edge can hold its profile for many
 * seconds after it has exited (EPERM even after 6 s of retries, 2026-10-18), so a folder still held is left in the
 * system's temporary folder, said on the console, rather than failing a test whose page did what it should. */
export function removeFolder(folder: string): void {
  try {
    rmSync(folder, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EPERM") throw error;
    console.warn(`left ${folder}: Edge still holds its profile`);
  }
}

/** A port nothing listens on now, as the system gives it. */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(typeof address === "object" && address ? address.port : 0));
    });
  });
}

/** A page of headless Edge, spoken to through the debugging protocol. */
export class Browser {
  private socket!: WebSocket;
  private next = 0;
  private readonly waiting = new Map<number, (value: { result?: unknown; error?: unknown }) => void>();

  constructor(private readonly process: ChildProcess) {}

  static async open(url: string, profile: string): Promise<Browser> {
    const port = await freePort();
    const process = spawn(EDGE!, [`--headless=new`, `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
      "--window-size=1100,800", "--allow-file-access-from-files", "--no-first-run", "about:blank"], { windowsHide: true, stdio: "ignore" });
    process.unref(); // a browser left behind never keeps the tests from ending
    const browser = new Browser(process);
    let target: { webSocketDebuggerUrl: string } | undefined;
    for (let tries = 0; tries < 300 && !target; tries++) {
      try {
        const answer = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
        target = (await answer.json()) as { webSocketDebuggerUrl: string };
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
    }
    if (!target) {
      await browser.close();
      assert.fail(`Edge did not answer on port ${port}`);
    }
    browser.socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      browser.socket.onopen = resolve;
      browser.socket.onerror = reject;
    });
    browser.socket.onmessage = (event) => {
      const message = JSON.parse(String(event.data)) as { id?: number; result?: unknown; error?: unknown };
      if (message.id !== undefined) browser.waiting.get(message.id)?.(message);
    };
    return browser;
  }

  async send(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const id = ++this.next;
    const answer = await new Promise<{ result?: unknown; error?: unknown }>((resolve) => {
      this.waiting.set(id, resolve);
      this.socket.send(JSON.stringify({ id, method, params }));
    });
    assert.equal(answer.error, undefined, `${method} failed: ${JSON.stringify(answer.error)}`);
    return answer.result;
  }

  async evaluate<T>(expression: string): Promise<T> {
    const result = (await this.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })) as {
      result: { value: T };
      exceptionDetails?: unknown;
    };
    assert.equal(result.exceptionDetails, undefined, `the page failed on: ${expression}`);
    return result.result.value;
  }

  async until(expression: string): Promise<void> {
    for (let tries = 0; tries < 600; tries++) {
      if (await this.evaluate<boolean>(expression)) return;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    assert.fail(`never true: ${expression}`);
  }

  async mouse(type: string, x: number, y: number): Promise<void> {
    await this.send("Input.dispatchMouseEvent", { type, x, y, button: "left", buttons: type === "mouseReleased" ? 0 : 1, clickCount: 1 });
  }

  async click(x: number, y: number): Promise<void> {
    await this.mouse("mousePressed", x, y);
    await this.mouse("mouseReleased", x, y);
  }

  /** Close the page and end Edge with every process it started, waiting until it has (it holds its profile folder
   * until then). */
  async close(): Promise<void> {
    this.socket?.close();
    const ended = new Promise((resolve) => this.process.once("exit", resolve));
    if (process.platform === "win32" && this.process.pid !== undefined) {
      spawnSync("taskkill", ["/PID", String(this.process.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
    } else {
      this.process.kill();
    }
    await Promise.race([ended, new Promise((resolve) => setTimeout(resolve, 5000))]);
  }
}

/** A page of media/ as the extension fills it in (`{{source}}`, `{{nonce}}`, and each file's address), written to the
 * folder with the stand-in for VS Code's webview API; its address. */
export function webviewPage(folder: string, template: string, files: Record<string, string>): string {
  const stub = '<script nonce="test">window.posted = []; window.acquireVsCodeApi = () => ' +
    "({ postMessage: (message) => window.posted.push(message), getState: () => undefined, setState: () => {} });</script>";
  let html = readFileSync(path.join(MEDIA, template), "utf-8").replaceAll("{{source}}", "file:").replaceAll("{{nonce}}", "test");
  html = html.replace("{{tokens}}", pathToFileURL(path.join(MEDIA, "tokens.css")).toString()); // every page's tokens
  for (const [field, name] of Object.entries(files)) {
    html = html.replace(`{{${field}}}`, pathToFileURL(path.join(MEDIA, name)).toString());
  }
  html = html.replace('<script nonce="test" src=', `${stub}
    <script nonce="test" src=`);
  const file = path.join(folder, template);
  writeFileSync(file, html, "utf-8");
  return pathToFileURL(file).toString();
}
