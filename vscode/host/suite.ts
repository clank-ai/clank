// Design 0002 §3.2 and decision 0029: inside a real VS Code, the extension activates and registers every command its
// manifest declares; with no service for its CLANK_HOME its status bar says the service is not running; and once a
// service answers (a small fake of the API's routes) the status bar shows the service, what the main slot runs
// (design 0003 §8.3) and Docker's state.

import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { join } from "node:path";

import * as vscode from "vscode";

import type { ClankExtension } from "../src/extension";

const TOKEN = "host-suite-token";
const ROUTES: Record<string, unknown> = {
  history: [],
  service: { version: "0.0.0", url: "", started: "2026-10-12T00:00:00.000Z", clients: [] },
  docker: { label: "Docker Desktop", state: "running", summary: "Docker Desktop · running · no container" },
  questions: [],
  "runtime/slots": [
    {
      name: "main", status: "ready", since: "2026-10-12T00:00:00.000Z", reason: "small 32K answered in 11 s",
      preset: "small-32k", launch_id: 1, host: "ubuntu-22.04", pid: 971, started: null, command: null, port: 18200,
      last_good: null,
    },
  ],
  "runtime/presets": [
    {
      id: "small-32k", title: "small 32K", engine: "kvmem-llamacpp", engine_version: "v0.16.0-rc1",
      model: "qwen3.8-27b", options: {}, slot: "main", host: "", notes: "", source: "default", file: "", problems: [],
    },
  ],
};

/** VS Code's test runner calls this; a thrown error fails the run. */
export async function run(): Promise<void> {
  const extension = vscode.extensions.getExtension<ClankExtension>("clank.clank");
  assert.ok(extension, "VS Code knows the extension");
  const clank = await extension.activate();
  const commands = await vscode.commands.getCommands(true);
  const manifest = extension.packageJSON as { contributes: { commands: Array<{ command: string }> } };
  for (const { command } of manifest.contributes.commands) {
    assert.ok(commands.includes(command), `${command} is registered`);
  }
  await until(() => clank.status().clank.includes("not running"), "the status bar says the service is not running");

  const service = await fakeService();
  try {
    const home = process.env["CLANK_HOME"];
    assert.ok(home, "the runner sets CLANK_HOME");
    const { port } = service.address() as AddressInfo;
    mkdirSync(join(home, "state"), { recursive: true });
    writeFileSync(join(home, "state", "local.token"), `${TOKEN}\n`);
    writeFileSync(join(home, "state", "connection.json"), JSON.stringify({ url: `http://127.0.0.1:${port}` }));
    await vscode.commands.executeCommand("clank.reconnect");
    await until(() => clank.status().docker.includes("Docker: running"), "the status bar shows Docker running");
    assert.doesNotMatch(clank.status().clank, /not running/);
    assert.match(clank.status().clank, /Clank · small 32K/, "the status bar shows what the main slot runs");
  } finally {
    service.close();
  }
}

/** A service that answers the routes the extension reads, and holds an event stream open. */
async function fakeService(): Promise<Server> {
  const server = createServer((request: IncomingMessage, response: ServerResponse) => {
    if (request.headers.authorization !== `Bearer ${TOKEN}`) {
      response.writeHead(401).end();
      return;
    }
    const route = (request.url ?? "").replace(/^\/api\/v1\//, "").split("?")[0] ?? "";
    if (route === "events") {
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      response.write("event: connected\ndata: {}\n\n");
      return;
    }
    if (!(route in ROUTES)) {
      response.writeHead(404).end();
      return;
    }
    response.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(ROUTES[route]));
  });
  await new Promise<void>((ready) => server.listen(0, "127.0.0.1", ready));
  return server;
}

async function until(holds: () => boolean, what: string, ms = 20_000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!holds()) {
    if (Date.now() > deadline) {
      throw new Error(`never: ${what}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}
