// The agent panel's decisions about the stream it follows (design 0023 §5), pure so Node tests them: which parameters
// open the stream (resumed from its version only on the same session), how long to wait before a broken stream is
// opened again (doubled each time, up to eight seconds), when the panel gives up on the stream and polls the route
// instead (three failures in a row), what the header says of the link, and which older pages the owner read stay
// through a snapshot (the same session's: all of them; another session's: none).

import type { Conversation, PageMessage } from "./conversation";
import type { Talk } from "./talking";

export const RETRY_MS = 1000; // the first wait before a broken stream is opened again
export const RETRY_MOST_MS = 8000;
export const FAILURES_TO_POLL = 3;

/** The stream route's parameters: the folder, the session pinned (or "" for the folder's newest), the page's size,
 * and, when the live state holds a version of the session to be opened, `after` and `after_session` to resume. */
export function streamParameters(
  talk: Talk,
  folder: string,
  pinned: string,
  limit: number,
): Record<string, string | number> {
  const shown = talk.conversation?.session?.id ?? "";
  const resumable = talk.version > 0 && shown !== "" && (pinned === "" || pinned === shown);
  return {
    folder,
    session: pinned,
    limit,
    ...(resumable ? { after: talk.version, after_session: shown } : {}),
  };
}

/** The wait before the next try, after one of `wait`. */
export function nextWait(wait: number): number {
  return Math.min(wait * 2, RETRY_MOST_MS);
}

/** Whether `failures` stream failures in a row mean the panel polls the route instead. */
export function pollsAfter(failures: number): boolean {
  return failures >= FAILURES_TO_POLL;
}

/** What the header says of the link: nothing while the stream flows. */
export function headerLink(polling: boolean, failures: number): string {
  return polling ? "polling" : failures > 0 ? "reconnecting…" : "";
}

/** The older pages and the cursor after a snapshot: the same session's keeps them (the cursor is theirs while there
 * are some, else the snapshot's); another session's starts over. `before` is the session shown before the snapshot. */
export function pagesAfterSnapshot(
  before: string | undefined,
  found: Conversation | null,
  older: PageMessage[],
  cursor: string,
): { older: PageMessage[]; cursor: string } {
  const next = found?.next ?? "";
  if (found?.session?.id !== before || !older.length) {
    return { older: [], cursor: next };
  }
  return { older, cursor };
}
