// Comments on the LaTeX source (design 0020 §11): VS Code's comment threads on lines of .tex files, sent to the agent
// together through the service (`POST /agents/latex/comments`), each with its file, its lines (from 1), the text it
// covers and its words; the service numbers them, and each thread is then labeled with its number. Pure: the threads
// themselves are extension.ts's.

import type { Api } from "./controller";

/** A comment thread as the send needs it: its file (from the folder), its lines (from 0, as VS Code counts), the text it
 * covers, its comments' words, and whether it was sent. */
export interface CommentThreadView {
  file: string;
  start: number;
  end: number;
  text: string;
  bodies: string[];
  sent: boolean;
}

/** Send the threads not sent yet; which thread (by its place in `threads`) got which number, or the error to say. */
export async function sendComments(
  api: Api,
  folder: string,
  threads: CommentThreadView[],
  message = "",
): Promise<{ numbered: Map<number, number>; text: string } | { error: string }> {
  const chosen = threads
    .map((thread, index) => ({ thread, index, body: thread.bodies.map((each) => each.trim()).filter(Boolean).join("\n") }))
    .filter(({ thread, body }) => !thread.sent && body);
  if (!chosen.length) {
    return { error: "No comment to send: comment on a line of a .tex file first." };
  }
  const comments = chosen.map(({ thread, body }) => ({
    file: thread.file,
    start: thread.start + 1,
    end: thread.end + 1,
    text: thread.text,
    body,
  }));
  try {
    await api.post("agents/latex/comments", { folder, message, comments });
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
  const numbered = new Map(chosen.map(({ index }, place) => [index, place + 1]));
  const count = chosen.length;
  return { numbered, text: `${count} comment${count === 1 ? "" : "s"} sent to the agent` };
}
