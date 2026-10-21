// Where the Clank service answers, and the local token that proves the caller is the user (design 0002 §2.7).
// CLANK_HOME comes from the extension's setting, else the environment, else `.clank` in the home folder. The service
// writes `state/connection.json` when it starts and removes it when it stops; `state/local.token` is readable only by
// the user. Both are read each time the extension connects and never kept, so the extension holds nothing of its own.

import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Where the service answers, and the token to call it with. */
export interface Connection {
  url: string;
  token: string;
}

/** CLANK_HOME: the setting when it names one, else the environment's, else `.clank` in the home folder. */
export function clankHome(setting: string | undefined, environment: NodeJS.ProcessEnv, homedir: string): string {
  if (setting?.trim()) {
    return setting.trim();
  }
  const fromEnvironment = environment["CLANK_HOME"]?.trim();
  return fromEnvironment || join(homedir, ".clank");
}

/** The running service's address and the local token, or undefined when the service is not running. */
export function readConnection(home: string): Connection | undefined {
  try {
    const written = JSON.parse(readFileSync(join(home, "state", "connection.json"), "utf8")) as { url?: unknown };
    const token = readFileSync(join(home, "state", "local.token"), "utf8").trim();
    return typeof written.url === "string" && token ? { url: written.url, token } : undefined;
  } catch {
    return undefined;
  }
}
