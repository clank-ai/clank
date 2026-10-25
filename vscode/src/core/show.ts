// The files the agent opens for the owner (design 0018 §7): the service's event `agents.shown` names a workspace's
// folder on this machine and the files, from the folder, that a window on that folder opens on the left, beside the
// agent (`shown`, `sameFolder`). The agent prints paths as its container sees them, under `/workspace/`; in its
// terminal each becomes a link to the folder's file (`containerLinks`). Pure: `extension.ts` does the opening.

import type { ServerEvent } from "./events";

/** Files the agent opened for the owner: its workspace, the folder on this machine, the files from it, and why. */
export interface Shown {
  workspace: string;
  folder: string;
  files: string[];
  why: string;
}

/** A path under `/workspace/` in a line of the agent's terminal: where it starts, its length, and the file from the
 * folder. */
export interface ContainerLink {
  start: number;
  length: number;
  relative: string;
}

const CONTAINER = "/workspace/";
// A path under /workspace/ not inside a longer path (`/data/workspace/x` is none), up to a space, a quote or a bracket.
const LINK = /(?<![\w./-])\/workspace\/([^\s"'`()<>[\]{}|,;]+)/g;
const ENDING = /[.:;!?]+$/; // the punctuation a sentence ends with
const LINE = /:\d+(:\d+)?$/; // a line, or a line and a column, after the path

/** The files an `agents.shown` event names; undefined for any other event, or one that names none. */
export function shown(message: ServerEvent): Shown | undefined {
  if (message.name !== "agents.shown") {
    return undefined;
  }
  const data = ((message.data ?? {}) as { data?: Partial<Shown> }).data ?? {};
  const files = Array.isArray(data.files) ? data.files.filter((each): each is string => typeof each === "string") : [];
  if (typeof data.folder !== "string" || !files.length) {
    return undefined;
  }
  return { workspace: String(data.workspace ?? ""), folder: data.folder, files, why: String(data.why ?? "") };
}

/** Whether two folders are the same: either slash, with or without a trailing one; on Windows, whatever the case. */
export function sameFolder(one: string, other: string, windows: boolean): boolean {
  const plain = (folder: string): string => {
    const slashed = folder.replace(/\\/g, "/").replace(/\/+$/, "");
    return windows ? slashed.toLowerCase() : slashed;
  };
  return plain(one) === plain(other);
}

/** The paths under `/workspace/` in a line, each a file of the folder (none outside it, no folder itself). */
export function containerLinks(line: string): ContainerLink[] {
  const found: ContainerLink[] = [];
  for (const match of line.matchAll(LINK)) {
    const relative = match[1]!.replace(ENDING, "").replace(LINE, "").replace(ENDING, "");
    if (!relative || relative.endsWith("/") || relative.split("/").includes("..")) {
      continue;
    }
    found.push({ start: match.index!, length: CONTAINER.length + relative.length, relative });
  }
  return found;
}
