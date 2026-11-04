// Where the Clank service answers, and the local token that proves the caller is the user (design 0002 §2.7).
// CLANK_HOME comes from the extension's setting, else the environment, else `.clank` in the home folder. The service
// writes `state/connection.json` when it starts and removes it when it stops; `state/local.token` is readable only by
// the user. Both are read each time the extension connects and never kept, so the extension holds nothing of its own.
// Decision 0156: the setting is the user's alone (`userSetting`: a folder's own settings never choose CLANK_HOME), and
// only a service on this machine is trusted (`onThisMachine`), as the service listens and answers only there; any other
// address is refused, saying why, and the local token is never sent to it.

import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Where the service answers, and the token to call it with. */
export interface Connection {
  url: string;
  token: string;
}

/** A setting as VS Code's `inspect` gives it: its value in the user's settings, the workspace's and the folder's. */
export interface Inspected<T> {
  globalValue?: T;
  workspaceValue?: T;
  workspaceFolderValue?: T;
}

/** A setting's value in the user's settings (in a remote window, with the remote machine's) alone: the workspace's and
 * the folder's own values are never read, so a folder cannot choose CLANK_HOME or start the agent. */
export function userSetting<T>(inspected: Inspected<T> | undefined): T | undefined {
  return inspected?.globalValue;
}

/** CLANK_HOME: the setting when it names one, else the environment's, else `.clank` in the home folder. */
export function clankHome(setting: string | undefined, environment: NodeJS.ProcessEnv, homedir: string): string {
  if (setting?.trim()) {
    return setting.trim();
  }
  const fromEnvironment = environment["CLANK_HOME"]?.trim();
  return fromEnvironment || join(homedir, ".clank");
}

/** The host names of this machine the service answers to (design 0002 §2.7). */
const THIS_MACHINE = new Set(["127.0.0.1", "localhost", "[::1]"]);

/** Whether an address is the service's on this machine: http to 127.0.0.1, localhost or [::1], with no user name. */
export function onThisMachine(url: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  return parsed.protocol === "http:" && !parsed.username && !parsed.password && THIS_MACHINE.has(parsed.hostname);
}

/** The running service's address and the local token; undefined when the service is not running, or when the address
 * is not on this machine (`refused` hears why). */
export function readConnection(home: string, refused: (why: string) => void = () => undefined): Connection | undefined {
  const file = join(home, "state", "connection.json");
  let written: { url?: unknown };
  let token: string;
  try {
    written = JSON.parse(readFileSync(file, "utf8")) as { url?: unknown };
    token = readFileSync(join(home, "state", "local.token"), "utf8").trim();
  } catch {
    return undefined;
  }
  if (typeof written.url !== "string" || !token) {
    return undefined;
  }
  if (!onThisMachine(written.url)) {
    refused(
      `${file} names ${written.url}: the extension trusts only a service on this machine (http to 127.0.0.1, ` +
        "localhost or [::1]), so it does not connect. Check the setting clank.home (user settings) and CLANK_HOME.",
    );
    return undefined;
  }
  return { url: written.url, token };
}
