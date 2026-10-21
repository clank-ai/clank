// Completion in VS Code (design 0006 §5): gray text after the cursor, from the model in the fast slot, through the
// gateway's fill in the middle (`POST /v1/infill`). It asks only while completion is on and its slot serves, once the
// user has stopped typing for the setting's wait (a request VS Code no longer needs is canceled, and the gateway breaks
// off any older one), not when the rest of the line holds more than closing brackets and quotes. It sends the text
// before the current line (up to 120 lines), the current line up to the cursor, and what follows (up to 20 lines): the
// form measured on 2026-10-15. One line, or a few on an empty line after one that opens a block when the setting says
// so. The status bar item says whether completion is on and served; a click turns it off or on for every window (the
// service's `completion` settings, which the console's Completion page shows too).

import type { Api } from "./controller";
import type { ServerEvent } from "./events";

/** Completion, as `GET /api/v1/gateway/completion` gives it (the part this uses). */
export interface CompletionView {
  settings: { enabled: boolean; delay_ms: number; lines: "one" | "few" };
  slot: { status: string; reason: string };
  url: string;
  problem: string;
}

/** What is sent to the gateway's `/v1/infill`, in llama.cpp's own fields. */
export interface InfillBody {
  model: string;
  input_prefix: string;
  prompt: string;
  input_suffix: string;
  n_predict: number;
  stop: string[];
  cache_prompt: boolean;
}

/** VS Code, as completion sees it: its status bar item, and a message. */
export interface CompletionPresenter {
  completion(text: string, tooltip: string, shown: boolean): void;
  info(text: string): void;
  warn(text: string): void;
}

const BEFORE_LINES = 120;
const BEFORE_CHARS = 6000;
const AFTER_LINES = 20;
const AFTER_CHARS = 1500;
const ONE_LINE = 32; // tokens
const FEW_LINES = 64;
const CLOSING = /^[\s)\]}>'"`;,]*$/; // the rest of a line that still leaves room for a suggestion
const OPENS = /[:{([]\s*$/; // a line that opens a block

/** Whether to ask, by the rest of the current line after the cursor. */
export function wanted(restOfLine: string): boolean {
  return CLOSING.test(restOfLine);
}

/** The request for the text before and after the cursor (line ends as `\n`). */
export function infill(before: string, after: string, lines: "one" | "few"): InfillBody {
  const start = before.lastIndexOf("\n") + 1;
  const current = before.slice(start);
  const above = before.slice(0, start);
  const kept = above.split("\n").slice(-BEFORE_LINES - 1).join("\n");
  const prefix = kept.slice(-BEFORE_CHARS);
  const suffix = after.split("\n").slice(0, AFTER_LINES + 1).join("\n").slice(0, AFTER_CHARS);
  const previous = above.replace(/\n$/, "").split("\n").pop() ?? "";
  const few = lines === "few" && current.trim() === "" && OPENS.test(previous);
  return {
    model: "completion",
    input_prefix: prefix,
    prompt: current,
    input_suffix: suffix,
    n_predict: few ? FEW_LINES : ONE_LINE,
    stop: few ? ["\n\n"] : ["\n"],
    cache_prompt: true,
  };
}

/** The suggestion in an answer: its text, one line when one was asked, without trailing spaces. */
export function suggestion(answer: unknown, body: InfillBody): string {
  const content = (answer as { content?: unknown } | null)?.content;
  const text = typeof content === "string" ? content : "";
  return (body.stop[0] === "\n" ? (text.split("\n")[0] ?? "") : text).replace(/\s+$/, "");
}

/** Completion in this window. */
export class Completer {
  view: CompletionView | undefined;

  constructor(
    private readonly presenter: CompletionPresenter,
    private readonly fetcher: typeof fetch = fetch,
    private readonly sleep: (ms: number) => Promise<void> = (ms) => new Promise((done) => setTimeout(done, ms)),
  ) {}

  /** Whether completion is on and its slot serves. */
  serving(): boolean {
    return Boolean(this.view?.settings.enabled && this.view.slot.status === "ready");
  }

  /** On connecting: completion's settings and its slot. */
  async load(api: Api): Promise<void> {
    try {
      this.view = await api.get<CompletionView>("gateway/completion");
    } catch {
      this.view = undefined; // a service from before completion
    }
    this.draw();
  }

  /** An event: read again when a slot changed or completion's settings did. */
  async event(api: Api, message: ServerEvent): Promise<void> {
    const subject = (message.data as { subject?: { kind?: string } } | undefined)?.subject?.kind;
    if (message.name === "runtime.slot" || (message.name.startsWith("settings.") && subject === "completion")) {
      await this.load(api);
    }
  }

  /** Not connected: nothing to show, nothing asked. */
  disconnected(): void {
    this.view = undefined;
    this.draw();
  }

  /** Turn completion off or on, for every window. */
  async toggle(api: Api): Promise<void> {
    if (!this.view) {
      await this.load(api);
    }
    const on = !this.view?.settings.enabled;
    try {
      this.view = await api.post<CompletionView>("gateway/completion", { enabled: on });
    } catch (error) {
      this.presenter.warn(error instanceof Error ? error.message : String(error));
      return;
    }
    this.draw();
    this.presenter.info(on ? "Completion is on." : "Completion is off: nothing is asked.");
  }

  /** The suggestion at the cursor, once the user has stopped typing; undefined when there is none to show (not
   * serving, the rest of the line in the way, canceled, nothing written, or the gateway refused). */
  async complete(
    read: () => { before: string; after: string },
    canceled: () => boolean,
    signal?: AbortSignal,
  ): Promise<string | undefined> {
    const view = this.view;
    if (!view || !this.serving()) {
      return undefined;
    }
    await this.sleep(view.settings.delay_ms);
    if (canceled()) {
      return undefined;
    }
    const { before, after } = read();
    if (!wanted(after.split("\n")[0] ?? "")) {
      return undefined;
    }
    const body = infill(before, after, view.settings.lines);
    try {
      const answer = await this.fetcher(`${view.url}/infill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });
      if (!answer.ok || canceled()) {
        return undefined;
      }
      return suggestion(await answer.json(), body) || undefined;
    } catch {
      return undefined; // canceled, or the gateway does not answer: the next keystroke asks again
    }
  }

  private draw(): void {
    const view = this.view;
    if (!view) {
      this.presenter.completion("", "", false);
      return;
    }
    if (!view.settings.enabled) {
      this.presenter.completion("$(circle-slash) Completion", "Completion is off: click to turn it on.", true);
    } else if (view.slot.status !== "ready") {
      const tip = `Completion is on, but its model does not run (${view.slot.status}): F8 in the console loads it. Click to turn completion off.`;
      this.presenter.completion("$(warning) Completion", tip, true);
    } else {
      const tip = "Completion is on: gray text after the cursor as you type; Tab takes it. Click to turn it off.";
      this.presenter.completion("$(check) Completion", tip, true);
    }
  }
}
