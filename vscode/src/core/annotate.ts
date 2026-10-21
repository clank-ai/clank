// Sending a figure the owner marked up (design 0008 §5-§6): what the annotator page sends, passed to the service
// (`POST /api/v1/agents/annotations`), which sends it to the workspace's agent; and what the page then says.

import type { Api } from "./controller";

/** A marked-up figure: the folder the window has open, the figure's file, the marks, the message, the copy (PNG). */
export interface Annotation {
  folder: string;
  figure: string;
  marks: unknown[];
  message: string;
  image: string;
}

/** Where it went, as the service says. */
export interface Sent {
  workspace: string;
  port: number;
  session: string;
  annotation: string;
  text: string;
  attached: boolean;
}

/** What the page says once it is sent. */
export function sentLine(sent: Sent): string {
  return sent.attached
    ? `Sent to the agent of ${sent.workspace}, with the marked-up figure.`
    : `Sent to the agent of ${sent.workspace}: the marks in words (its model reads no images).`;
}

/** Send an annotation; the line the page shows, and whether it went. */
export async function annotate(api: Api, annotation: Annotation): Promise<{ ok: boolean; text: string }> {
  try {
    const sent = await api.post<Sent>("agents/annotations", annotation);
    return { ok: true, text: sentLine(sent) };
  } catch (error) {
    return { ok: false, text: error instanceof Error ? error.message : String(error) };
  }
}
