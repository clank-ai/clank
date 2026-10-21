// Reviewing the agent's changes in VS Code (design 0007 §6). A question about a change in the window's folder opens as
// a diff beside the files (the file as it is, as the agent would leave it), not as a notification; Accept and Reject
// answer it (a reject may tell the agent why), from the editor's title bar or the commands; when it is settled anywhere
// the diff closes (one settled while it is being opened never opens, and on loading a diff left open from before whose
// question no longer waits closes: a window reloaded after an answer). In auto mode each change made in the window's folder opens after it is made (the file before and
// after), when the setting says so. The mode of the window's workspace shows in the status bar, and a click switches
// it. Like the controller, it speaks to VS Code only through its presenter, so it is tested without VS Code.

import type { Api } from "./controller";
import type { ServerEvent } from "./events";
import type { Question } from "./kinds";
import type { Choice } from "./presenter";

/** A change, as `GET /api/v1/agents/changes/{id}` gives it. */
export interface ChangeView {
  id: string;
  workspace: string;
  relative: string;
  path: string;
  folder: string;
  before: string | null;
  after: string | null;
  made: string | null;
  diff: string;
  additions: number;
  deletions: number;
  created: boolean;
  exact: boolean;
  state: string;
  mode: string;
  problem: string;
}

/** A workspace's mode, as `GET /api/v1/agents/review` gives it (`workspace` null: the folder has none). `agent` is the
 * agent of OpenCode's window as last seen, and `shown` what the status bar shows: "plan" when that is the planner, else
 * the mode. A service from before plan mode gives neither. */
export interface ReviewView {
  workspace: string | null;
  mode: "review" | "auto";
  agent?: "planner" | "build" | null;
  shown?: "plan" | "review" | "auto";
  waiting: number;
  watching: boolean;
  problem: string;
}

/** VS Code, as the review sees it. */
export interface ReviewPresenter {
  /** The mode's item of the status bar: its text and tooltip, or hidden. */
  mode(text: string, tooltip: string, shown: boolean): void;
  /** Open a change waiting for review beside the files, answered through its question. */
  review(change: ChangeView, question: string, title: string): void;
  /** Close the change of a question settled. */
  reviewed(question: string): void;
  /** The questions of the changes open for review in the window (restored with it too). */
  openReviews(): string[];
  /** Open a change made in auto mode beside the files, without taking the keyboard. */
  changed(change: ChangeView, title: string): void;
  /** Ask what to tell the agent with a reject: the words (maybe none), or undefined to keep the change waiting. */
  note(): Promise<string | undefined>;
  /** Let the user pick one of these; undefined when the pick was dismissed. */
  pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined>;
  info(text: string): void;
  warn(text: string): void;
}

/** What the review needs of the window: its folders, and whether auto mode's changes are shown. */
export interface ReviewOptions {
  folders: () => string[];
  showInAuto: () => boolean;
  caseless?: boolean;
}

interface EventData {
  subject?: { kind?: string; id?: string } | null;
  data?: { folder?: string; file?: string; mode?: string; change?: string; workspace?: string };
}

const SETTLED = new Set(["question.answered", "question.withdrawn", "question.expired"]);
const MODE_EVENTS = new Set([
  "agents.review_switched",
  "agents.mode_switched",
  "agents.agent_seen",
  "agents.change_proposed",
  "agents.change_answered",
]);

/** The three modes of the status bar. */
export type Shown = "plan" | "review" | "auto";
const MODES: Array<{ id: Shown; label: string; description: string }> = [
  { id: "plan", label: "Plan", description: "the Planner: writes plans in Markdown, no code, no runs" },
  { id: "review", label: "Review", description: "Build; you accept or reject each change" },
  { id: "auto", label: "Auto", description: "Build; changes are made without asking" },
];

/** What the status bar shows for a view: its `shown`, else its mode. */
export function shownMode(view: ReviewView): Shown {
  return view.shown ?? view.mode;
}

/** The items of the mode pick, the current one marked. */
export function modeChoices(view: ReviewView): Array<Choice<Shown>> {
  const current = shownMode(view);
  return MODES.map((each) => ({
    label: each.id === current ? `$(check) ${each.label}` : each.label,
    detail: each.description,
    value: each.id,
  }));
}

/** Whether a question is about a change (shown as a review, not as a notification). */
export function aboutChange(question: Question): boolean {
  return question.about?.kind === "change";
}

/** The title of a change's tab: to review, or made in auto mode. */
export function changeTitle(change: ChangeView, made: boolean): string {
  const lines = [change.additions ? `+${change.additions}` : "", change.deletions ? `-${change.deletions}` : ""];
  const counts = change.created ? "new file" : lines.filter(Boolean).join(" ") || "no lines";
  return `${made ? "Changed" : "Review"}: ${change.relative} (${counts})`;
}

/** The mode's item: its text and tooltip for a workspace's view. */
export function modeItem(view: ReviewView): { text: string; tooltip: string } {
  const agent = `the agent of ${view.workspace}`;
  const shown = shownMode(view);
  const means: Record<Shown, string> = {
    plan: `Plan: ${agent} is the Planner: it writes plans in Markdown, with no code and no runs.`,
    auto: `Auto: ${agent} changes files without asking; each change opens beside your files after it is made.`,
    review: `Review: ${agent} asks before it changes a file; the change opens beside your files to accept or reject.`,
  };
  const tooltip =
    `${means[shown]} Click to pick Plan, Review or Auto. Tab in OpenCode switches Build and Planner too ` +
    "(Clank sees that once a message is sent).";
  const waiting = view.waiting === 1 ? " 1 change waits for you." : view.waiting ? ` ${view.waiting} changes wait.` : "";
  const watched = view.problem ? ` Not followed here now: ${view.problem}.` : "";
  const text = { plan: "$(note) Plan", auto: "$(zap) Auto", review: "$(eye) Review" }[shown];
  return { text, tooltip: tooltip + waiting + watched };
}

/** Whether `inner` is the folder `outer` or inside it. */
export function within(inner: string, outer: string, caseless: boolean): boolean {
  const plain = (path: string): string => {
    const slashed = path.replace(/\\/g, "/").replace(/\/+$/, "");
    return caseless ? slashed.toLowerCase() : slashed;
  };
  const [one, other] = [plain(inner), plain(outer)];
  return one === other || one.startsWith(other + "/");
}

/** The review of the agent's changes in this window. */
export class Reviews {
  view: ReviewView | undefined;
  private readonly open = new Map<string, ChangeView>();
  /** Questions being opened (their change is being read), and those of them settled meanwhile. */
  private readonly opening = new Set<string>();
  private readonly settledWhileOpening = new Set<string>();
  private readonly caseless: boolean;

  constructor(
    private readonly presenter: ReviewPresenter,
    private readonly options: ReviewOptions,
  ) {
    this.caseless = options.caseless ?? process.platform === "win32";
  }

  /** On connecting: the mode of the window's workspace, and the changes waiting in its folder opened. */
  async load(api: Api, questions: Question[]): Promise<void> {
    await this.readMode(api);
    const waiting = new Set(questions.filter(aboutChange).map((question) => question.id));
    for (const left of this.presenter.openReviews().filter((id) => !waiting.has(id))) {
      this.presenter.reviewed(left);
    }
    for (const question of questions.filter(aboutChange)) {
      await this.offer(api, question);
    }
  }

  /** A question about a change: opened when the change is in the window's folder (another window shows the rest). */
  async offer(api: Api, question: Question): Promise<void> {
    if (this.open.has(question.id) || this.opening.has(question.id) || !question.about) {
      return;
    }
    this.opening.add(question.id);
    const change = await this.change(api, question.about.id);
    this.opening.delete(question.id);
    if (this.settledWhileOpening.delete(question.id)) {
      return; // answered (in the terminal, on the phone) before its change was read: nothing to open
    }
    if (change && this.here(change.folder, change.path)) {
      this.open.set(question.id, change);
      this.presenter.review(change, question.id, changeTitle(change, false));
    }
  }

  /** An event: a settled question's change closed, the mode read again, a change made in auto mode shown. */
  async event(api: Api, message: ServerEvent): Promise<void> {
    const data = (message.data ?? {}) as EventData;
    const id = data.subject?.id;
    if (SETTLED.has(message.name) && id) {
      if (this.open.delete(id)) {
        this.presenter.reviewed(id);
      } else if (this.opening.has(id)) {
        this.settledWhileOpening.add(id);
      }
    }
    if (MODE_EVENTS.has(message.name)) {
      await this.readMode(api);
    }
    const made = data.data;
    if (message.name === "agents.change_made" && made?.mode === "auto" && made.change && made.folder) {
      if (this.here(made.folder, `${made.folder}/${made.file ?? ""}`) && this.options.showInAuto()) {
        const change = await this.change(api, made.change);
        if (change) {
          this.presenter.changed(change, changeTitle(change, true));
        }
      }
    }
  }

  /** Accept a change: the one named, else the one open here (a pick when several are). */
  async accept(api: Api, question?: string): Promise<void> {
    const chosen = await this.which(question);
    if (chosen) {
      await this.answer(api, chosen, { option: "accept" });
    }
  }

  /** Reject a change, with what to tell the agent (Escape keeps it waiting). */
  async reject(api: Api, question?: string): Promise<void> {
    const chosen = await this.which(question);
    if (!chosen) {
      return;
    }
    const note = await this.presenter.note();
    if (note !== undefined) {
      await this.answer(api, chosen, { option: "reject", text: note.trim() });
    }
  }

  /** Pick the window's mode (Plan, Review or Auto) and set it; the answer's view is shown, its note said. */
  async switchMode(api: Api): Promise<void> {
    await this.readMode(api);
    const view = this.view;
    if (!view?.workspace) {
      this.presenter.info("This folder has no Clank workspace: `clank` in it makes one.");
      return;
    }
    const mode = await this.presenter.pick(modeChoices(view), "Clank mode");
    if (mode === undefined) {
      return;
    }
    try {
      const answer = await api.post<ReviewView & { note?: string }>("agents/mode", { workspace: view.workspace, mode });
      const { note, ...shown } = answer;
      this.view = shown;
      this.draw();
      if (note) {
        this.presenter.info(note);
      }
    } catch (error) {
      this.presenter.warn(error instanceof Error ? error.message : String(error));
    }
  }

  /** Not connected: nothing to show. */
  disconnected(): void {
    this.view = undefined;
    this.draw();
  }

  private async readMode(api: Api): Promise<void> {
    const folder = this.options.folders()[0];
    if (folder === undefined) {
      this.view = undefined;
    } else {
      try {
        this.view = await api.get<ReviewView>("agents/review", { folder });
      } catch {
        this.view = undefined; // a service from before the review
      }
    }
    this.draw();
  }

  private draw(): void {
    if (!this.view?.workspace) {
      this.presenter.mode("", "", false);
      return;
    }
    const { text, tooltip } = modeItem(this.view);
    this.presenter.mode(text, tooltip, true);
  }

  private async which(question?: string): Promise<string | undefined> {
    if (question !== undefined) {
      return question;
    }
    const open = [...this.open.entries()];
    if (open.length <= 1) {
      if (!open.length) {
        this.presenter.info("No change waits for you in this window.");
      }
      return open[0]?.[0];
    }
    return this.presenter.pick(
      open.map(([id, change]) => ({ label: changeTitle(change, false), detail: change.workspace, value: id })),
      "Which change?",
    );
  }

  private async answer(api: Api, question: string, body: { option: string; text?: string }): Promise<void> {
    try {
      await api.post(`questions/${question}/answer`, body);
    } catch (error) {
      this.presenter.warn(error instanceof Error ? error.message : String(error));
    }
  }

  private async change(api: Api, id: string): Promise<ChangeView | undefined> {
    try {
      return await api.get<ChangeView>(`agents/changes/${encodeURIComponent(id)}`);
    } catch (error) {
      this.presenter.warn(error instanceof Error ? error.message : String(error));
      return undefined;
    }
  }

  /** Whether a change is this window's: its file is in a folder the window has open, or the window has a folder of
   * its workspace open. */
  private here(folder: string, path: string): boolean {
    return this.options.folders().some((open) => within(path, open, this.caseless) || within(open, folder, this.caseless));
  }
}
