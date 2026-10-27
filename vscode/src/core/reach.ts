// Whether OpenCode reaches the model from the window's folder (design 0004 §5, revised 2026-10-26): what the service's
// `GET /agents/reach` answers (each check on the way: the workspace's container, the gateway, the gateway's host `edge`
// from inside the container, the model), put in words for the status bar (`reachStatus`), the agent panel and a
// notification (`reachNotice`). `blocked` means OpenCode would fail at once, so the agent is not started then; a fix is
// the route the service names, posted when the owner presses its button (`applyFix`). A service from before the route,
// or one too slow to say, gives nothing, and the agent starts as before. Pure but for the two calls.

import { inTime } from "./client";

/** A fix: its button's words, the route to post and its body. */
export interface ReachFix {
  label: string;
  post: string;
  body: Record<string, unknown>;
}

/** One check on the way: ok, wrong (false) or not known (null), in words. */
export interface ReachCheck {
  name: string;
  ok: boolean | null;
  said: string;
}

/** The service's answer. */
export interface Reach {
  workspace: string | null;
  ready: boolean;
  blocked: boolean;
  problem: string;
  fix: ReachFix | null;
  checks: ReachCheck[];
  seconds: number;
}

/** What reading the way and fixing it ask of the service. */
export interface ReachApi {
  get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T>;
  post<T>(path: string, body?: unknown, requestKey?: string): Promise<T>;
}

export const REACH_MS = 15_000; // the service's look from inside the container takes at most 8 s

/** The way to the model from a folder's (or a named) workspace, or undefined when the service cannot say. */
export async function readReach(
  api: ReachApi,
  parameters: { folder?: string; workspace?: string },
  ms: number = REACH_MS,
): Promise<Reach | undefined> {
  try {
    return await inTime(api.get<Reach>("agents/reach", parameters), ms, "the agent's way to the model");
  } catch {
    return undefined;
  }
}

/** A sentence: its first letter capitalized and a period at its end. */
function sentence(text: string): string {
  const trimmed = text.trim();
  const ended = /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
  return ended.charAt(0).toUpperCase() + ended.slice(1);
}

/** The status bar's words while something is wrong that stops OpenCode or that a fix mends; undefined otherwise (a
 * model loading is said by the readout already). */
export function reachStatus(reach: Reach | undefined): { text: string; tooltip: string } | undefined {
  if (!reach || reach.ready || (!reach.blocked && !reach.fix)) {
    return undefined;
  }
  const text = reach.blocked ? "$(error) OpenCode cannot reach the model" : "$(warning) No model runs";
  const click = reach.fix ? `\nClick: ${reach.fix.label}.` : "\nClick: look again.";
  return { text, tooltip: (reachNotice(reach)?.text ?? "") + click };
}

/** What the agent panel and a notification say: the problem as a sentence (a workspace's name kept as it is written),
 * and the fix's button ("" for none). */
export function reachNotice(reach: Reach | undefined): { text: string; action: string } | undefined {
  if (!reach || reach.ready) {
    return undefined;
  }
  const problem = reach.problem.trim().replace(/[.]$/, "");
  const text = reach.blocked ? `OpenCode cannot reach the model: ${problem}.` : sentence(problem);
  return { text, action: reach.fix?.label ?? "" };
}

/** Post the fix the service named, with a request key (a press sent twice starts one operation). */
export async function applyFix(api: ReachApi, fix: ReachFix, requestKey: string): Promise<unknown> {
  return api.post(fix.post, fix.body, requestKey);
}
