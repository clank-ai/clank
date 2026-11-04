// Design 0002 §2.7: the extension finds the service through CLANK_HOME (its setting, else the environment, else
// `.clank` in the home folder), reading the connection file and the local token each time; a missing or unreadable
// file means the service is not running. Revised 2026-11-04 (decision 0156): only a service on this machine is trusted
// (http to 127.0.0.1, localhost or [::1]; any other address is refused, saying why), and CLANK_HOME and whether the
// agent starts come from the user's settings alone: the manifest gives both settings machine scope and leaves them out
// of restricted mode, and the extension reads only their user value, so a folder's own settings never choose them.

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { clankHome, readConnection, userSetting } from "../src/core/connection";

test("the setting wins, then the environment, then .clank in the home folder", () => {
  assert.equal(clankHome("/set", { CLANK_HOME: "/env" }, "/folders/me"), "/set");
  assert.equal(clankHome("  ", { CLANK_HOME: "/env" }, "/folders/me"), "/env");
  assert.equal(clankHome(undefined, {}, "/folders/me"), join("/folders/me", ".clank"));
});

test("the connection file and the token are read when both are there", () => {
  const home = mkdtempSync(join(tmpdir(), "clank-home-"));
  assert.equal(readConnection(home), undefined);
  mkdirSync(join(home, "state"));
  writeFileSync(join(home, "state", "connection.json"), JSON.stringify({ url: "http://127.0.0.1:7720", pid: 1 }));
  assert.equal(readConnection(home), undefined);
  writeFileSync(join(home, "state", "local.token"), "secret-token\n");
  assert.deepEqual(readConnection(home), { url: "http://127.0.0.1:7720", token: "secret-token" });
  writeFileSync(join(home, "state", "connection.json"), "{ not json");
  assert.equal(readConnection(home), undefined);
});

test("only a service on this machine is trusted: any other address is refused, saying why", () => {
  const home = mkdtempSync(join(tmpdir(), "clank-home-"));
  mkdirSync(join(home, "state"));
  writeFileSync(join(home, "state", "local.token"), "secret-token\n");
  const written = (url: string): void =>
    writeFileSync(join(home, "state", "connection.json"), JSON.stringify({ url, pid: 1 }));
  for (const url of ["http://127.0.0.1:7720", "http://localhost:7720", "http://[::1]:7720"]) {
    written(url);
    assert.deepEqual(readConnection(home), { url, token: "secret-token" }, url);
  }
  const refusals: string[] = [];
  for (const url of [
    "http://192.168.1.20:7720",
    "http://clank.example.com:7720",
    "http://127.0.0.1.example.com:7720",
    "http://me@127.0.0.1:7720",
    "https://127.0.0.1:7720",
    "file:///C:/clank",
    "not a url",
  ]) {
    written(url);
    assert.equal(readConnection(home, (why) => refusals.push(why)), undefined, url);
  }
  assert.equal(refusals.length, 7, "each refusal is said");
  assert.match(refusals[0], /http:\/\/192\.168\.1\.20:7720/, "it names the address");
  assert.match(refusals[0], /only a service on this machine/, "and says why");
});

test("CLANK_HOME and whether the agent starts come from the user's settings alone, never a folder's", () => {
  assert.equal(userSetting({ globalValue: "/mine", workspaceValue: "/theirs", workspaceFolderValue: "/folder" }), "/mine");
  assert.equal(userSetting({ workspaceValue: "/theirs", workspaceFolderValue: "/folder" }), undefined);
  assert.equal(userSetting<boolean>({ workspaceFolderValue: true }), undefined);
  assert.equal(userSetting(undefined), undefined);
});

test("the manifest keeps those settings to the user's (machine scope), and restricted mode leaves them out", () => {
  const manifest = JSON.parse(readFileSync(join(__dirname, "..", "..", "package.json"), "utf8")) as {
    capabilities: { untrustedWorkspaces: { supported: unknown; restrictedConfigurations?: string[]; description?: string } };
    contributes: { configuration: { properties: Record<string, { scope?: string }> } };
  };
  const trusted = manifest.capabilities.untrustedWorkspaces;
  assert.equal(trusted.supported, "limited");
  assert.ok(trusted.description, "restricted mode says what it limits");
  for (const name of ["clank.home", "clank.agent.openOnStart"]) {
    assert.equal(manifest.contributes.configuration.properties[name].scope, "machine", name);
    assert.ok(trusted.restrictedConfigurations?.includes(name), name);
  }
});
