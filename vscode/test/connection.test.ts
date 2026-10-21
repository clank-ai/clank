// Design 0002 §2.7: the extension finds the service through CLANK_HOME (its setting, else the environment, else
// `.clank` in the home folder), reading the connection file and the local token each time; a missing or unreadable
// file means the service is not running.

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { clankHome, readConnection } from "../src/core/connection";

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
