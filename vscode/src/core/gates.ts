// Gates in VS Code (design 0013 §10, §14 step 7). A question about a flow (a gate, a YOU box, a failed box, a box whose
// *when done* waits, a batch of proposals) shows as a notification with its answers and, for the files it shows, two
// more buttons: Open, the file in the folder as it stands (what an approval takes, §8), the gate shown again once that
// file is saved (edit, then approve); and Diff, the last two tries' copies of the file in VS Code's diff, the gate shown
// again at once. An answer that takes words (send back's note, try again's words) asks for them first, and Escape keeps
// the gate waiting and shows it again. What a question shows comes from the service (`GET flows/waiting`), the tries'
// texts from `GET flows/<workspace>/<name>/copy`, so the extension knows none of the runner's rules; a question about a
// flow that no run names (a batch of proposals) shows with its options alone. A gate is shown once when it is asked
// (not again on reconnecting); the Questions command (the status bar's count) shows it again, even while its first
// notification still waits: VS Code moves a notification left unclicked to its notification center, where its promise
// stays pending, so a gate is never kept off the screen for one shown before, and the first of its notifications
// clicked answers it (a click on another then says who answered). A gate settled anywhere is never shown again: its
// diffs close, a save of its file brings nothing back, and a click on its notification still on screen (VS Code cannot
// close one) says who answered it instead of answering. Like the controller, it speaks to VS Code only through its
// presenter, so it is tested without VS Code.

import type { Api } from "./controller";
import type { ServerEvent } from "./events";
import type { Question } from "./kinds";
import type { Choice } from "./presenter";

/** A file a flow's question shows, as `GET flows/waiting` gives it. */
export interface WaitedFile {
  /** The file, from the folder, with '/'. */
  path: string;
  /** Its place in the folder, on the service's machine. */
  file: string;
  /** The box that wrote it (empty for none). */
  box: string;
  /** The tries of that box, in the run, that kept a copy of it. */
  tries: number[];
  exists: boolean;
}

/** What a flow's question shows, as `GET flows/waiting` gives it. */
export interface Waited {
  question: string;
  flow: string;
  workspace: string;
  name: string;
  title: string;
  run: number;
  box: string;
  box_title: string;
  type: string;
  /** What the run waits for: you, gate, failed or done. */
  kind: string;
  folder: string;
  files: WaitedFile[];
  /** The answers that take words, with what the words are for. */
  notes: Record<string, string>;
}

/** One side of a diff: the document's key (one per try and file) and its text. */
export interface Side {
  key: string;
  text: string;
}

/** What a button of a gate's notification does: answer with an option, open a file, or diff two tries of one. */
export type GateAction = { option: string } | { open: WaitedFile[] } | { diff: WaitedFile[] };

/** A button of a gate's notification. */
export interface GateButton {
  label: string;
  action: GateAction;
}

/** VS Code, as the gates see it. */
export interface GatePresenter {
  /** Show a gate as a notification with these buttons; the action of the one clicked, undefined when dismissed. */
  gate(question: string, text: string, buttons: GateButton[]): Promise<GateAction | undefined>;
  /** Open a file of the folder in the editor: a new one at its place when it does not exist yet. */
  open(file: string, exists: boolean): Promise<void>;
  /** Open two tries' copies in VS Code's diff, as documents of this question (closed when it is settled). */
  diff(question: string, before: Side, after: Side, title: string): void;
  /** Close the diffs of a question settled. */
  closeDiffs(question: string): void;
  /** Ask for an answer's words; undefined when Escape was pressed. */
  note(title: string, prompt: string): Promise<string | undefined>;
  /** Let the user pick one of these; undefined when the pick was dismissed. */
  pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined>;
  info(text: string): void;
  warn(text: string): void;
}

/** What the gates need of the window: whether its paths compare without case (Windows). */
export interface GateOptions {
  caseless?: boolean;
}

interface EventData {
  summary?: string;
  subject?: { kind?: string; id?: string } | null;
}

const SETTLED = new Set(["question.answered", "question.withdrawn", "question.expired"]);

/** Whether a question is about a flow (shown as a gate, not as a plain notification). */
export function aboutFlow(question: Question): boolean {
  return question.about?.kind === "flow";
}

/** A gate's notification: what was just done (`said`), its title, and its detail in one line. */
export function gateText(question: Question, said = ""): string {
  const detail = question.detail
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join(" ");
  const title = /[.?!:]$/.test(question.title) ? question.title : `${question.title}.`;
  return `${said}${title}${detail ? ` ${detail}` : ""}`;
}

/** The two tries a file's Diff compares: its last two that kept a copy. */
function lastTwo(file: WaitedFile): [number, number] | undefined {
  const [a, b] = file.tries.slice(-2);
  return a !== undefined && b !== undefined ? [a, b] : undefined;
}

/** A gate's buttons: its answers, then Open and Diff for the files it shows. */
export function gateButtons(question: Question, view: Waited | undefined): GateButton[] {
  const buttons: GateButton[] = question.options.map((option) => ({ label: option.label, action: { option: option.id } }));
  const files = view?.files ?? [];
  const [only] = files;
  if (only) {
    buttons.push({ label: files.length === 1 ? `Open ${only.path}` : "Open a file…", action: { open: files } });
  }
  const diffable = files.filter((file) => lastTwo(file) !== undefined);
  const [one] = diffable;
  if (one) {
    const [a, b] = lastTwo(one) ?? [0, 0];
    const label = diffable.length === 1 ? `Diff ${one.path}: try ${a} and try ${b}` : "Diff two tries…";
    buttons.push({ label, action: { diff: diffable } });
  }
  return buttons;
}

/** The gates of the flows, in this window. */
export class Gates {
  /** The questions about a flow waiting, by id, and what each shows. */
  private readonly asked = new Map<string, Question>();
  private readonly views = new Map<string, Waited>();
  /** Shown once when asked; those settled anywhere, with who settled them. */
  private readonly offered = new Set<string>();
  private readonly settled = new Map<string, string>();
  /** The files opened from a gate, by their place, until saved; the questions whose diffs are open. */
  private readonly editing = new Map<string, { question: string; path: string }>();
  private readonly diffed = new Set<string>();
  private readonly caseless: boolean;

  constructor(
    private readonly presenter: GatePresenter,
    options: GateOptions = {},
  ) {
    this.caseless = options.caseless ?? process.platform === "win32";
  }

  /** On connecting: every question about a flow waiting is shown (once); one that no longer waits is settled. */
  async load(api: Api, questions: Question[]): Promise<void> {
    const waiting = new Set(questions.filter(aboutFlow).map((question) => question.id));
    for (const id of [...this.asked.keys()].filter((each) => !waiting.has(each))) {
      this.settle(id, `${id} was answered while VS Code was not connected`);
    }
    for (const question of questions.filter(aboutFlow)) {
      await this.offer(api, question);
    }
  }

  /** A question about a flow asked: shown as a gate, once. */
  async offer(api: Api, question: Question): Promise<void> {
    if (!aboutFlow(question) || this.offered.has(question.id) || this.settled.has(question.id)) {
      return;
    }
    this.offered.add(question.id);
    this.asked.set(question.id, question);
    await this.read(api);
    void this.present(api, question.id, "");
  }

  /** Show a gate again (the Questions command picked it). */
  async show(api: Api, question: Question): Promise<void> {
    this.offered.add(question.id);
    this.asked.set(question.id, question);
    await this.read(api);
    void this.present(api, question.id, "");
  }

  /** A file was saved: the gate it was opened from comes back, once (edit, then approve). */
  async saved(api: Api, file: string): Promise<void> {
    const key = this.key(file);
    const opened = this.editing.get(key);
    if (opened === undefined) {
      return;
    }
    this.editing.delete(key);
    if (this.asked.has(opened.question)) {
      await this.read(api);
      void this.present(api, opened.question, `${opened.path} saved. `);
    }
  }

  /** An event: a question settled anywhere is never shown again, and its diffs close. */
  async event(_api: Api, message: ServerEvent): Promise<void> {
    const data = (message.data ?? {}) as EventData;
    const id = data.subject?.id;
    if (SETTLED.has(message.name) && id && (this.asked.has(id) || this.offered.has(id))) {
      this.settle(id, data.summary || `${id} was settled elsewhere`);
    }
  }

  private settle(id: string, said: string): void {
    this.settled.set(id, said);
    this.asked.delete(id);
    this.views.delete(id);
    for (const [key, opened] of [...this.editing.entries()]) {
      if (opened.question === id) {
        this.editing.delete(key);
      }
    }
    if (this.diffed.delete(id)) {
      this.presenter.closeDiffs(id);
    }
  }

  /** Show a gate's notification, and act on the button clicked. An earlier notification of the same gate may still
   * wait, unclicked, in VS Code's notification center (its promise pending): this one is shown all the same, since
   * the owner asked for it, and whichever is clicked first answers the gate. */
  private async present(api: Api, id: string, said: string): Promise<void> {
    const question = this.asked.get(id);
    if (question === undefined) {
      return;
    }
    const action = await this.presenter.gate(id, gateText(question, said), gateButtons(question, this.views.get(id)));
    if (action === undefined) {
      return; // dismissed: the status bar's count and the Questions command still reach it
    }
    const settled = this.settled.get(id);
    if (settled !== undefined) {
      this.presenter.info(`${settled}: nothing was sent from here.`);
      return;
    }
    if ("option" in action) {
      await this.choose(api, question, action.option);
    } else if ("open" in action) {
      await this.open(api, question, action.open);
    } else {
      await this.diff(api, question, action.diff);
    }
  }

  private async choose(api: Api, question: Question, option: string): Promise<void> {
    const prompt = this.views.get(question.id)?.notes[option];
    if (prompt === undefined) {
      await this.answer(api, question.id, { option });
      return;
    }
    const label = question.options.find((each) => each.id === option)?.label ?? option;
    const words = await this.presenter.note(`${question.title}: ${label}`, prompt);
    if (words === undefined) {
      void this.present(api, question.id, ""); // Escape: the gate still waits
      return;
    }
    const settled = this.settled.get(question.id);
    if (settled !== undefined) {
      this.presenter.info(`${settled}: nothing was sent from here.`);
      return;
    }
    await this.answer(api, question.id, { option, text: words.trim() });
  }

  private async open(api: Api, question: Question, files: WaitedFile[]): Promise<void> {
    const chosen = await this.which(files, "Open which file?", (file) => `written by ${file.box || "nobody yet"}`);
    if (chosen === undefined) {
      void this.present(api, question.id, "");
      return;
    }
    this.editing.set(this.key(chosen.file), { question: question.id, path: chosen.path });
    await this.presenter.open(chosen.file, chosen.exists);
  }

  private async diff(api: Api, question: Question, files: WaitedFile[]): Promise<void> {
    const view = this.views.get(question.id);
    const chosen = await this.which(files, "Diff which file's last two tries?", (file) => `${file.box}'s tries`);
    const tries = chosen ? lastTwo(chosen) : undefined;
    if (view !== undefined && chosen !== undefined && tries !== undefined) {
      try {
        const [before, after] = await Promise.all(tries.map((each) => this.copy(api, view, chosen, each)));
        if (before && after && !this.settled.has(question.id)) {
          const title = `${chosen.path}: try ${tries[0]} and try ${tries[1]} (${chosen.box}, ${view.title})`;
          this.diffed.add(question.id);
          this.presenter.diff(question.id, before, after, title);
        }
      } catch (error) {
        this.presenter.warn(error instanceof Error ? error.message : String(error));
      }
    }
    void this.present(api, question.id, "");
  }

  private async copy(api: Api, view: Waited, file: WaitedFile, attempt: number): Promise<Side | undefined> {
    const path = `flows/${encodeURIComponent(view.workspace)}/${encodeURIComponent(view.name)}/copy`;
    const found = await api.get<{ text?: string }>(path, { run: view.run, box: file.box, file: file.path, try: attempt });
    const key = `${view.flow}/run-${view.run}/${file.box}/try-${attempt}/${file.path}`;
    return found.text === undefined ? undefined : { key, text: found.text };
  }

  private async which(
    files: WaitedFile[],
    placeholder: string,
    detail: (file: WaitedFile) => string,
  ): Promise<WaitedFile | undefined> {
    if (files.length <= 1) {
      return files[0];
    }
    return this.presenter.pick(
      files.map((file) => ({ label: file.path, detail: detail(file), value: file })),
      placeholder,
    );
  }

  private async read(api: Api): Promise<void> {
    try {
      const found = await api.get<{ waiting: Waited[] }>("flows/waiting");
      for (const view of found.waiting ?? []) {
        this.views.set(view.question, view);
      }
    } catch {
      // a service from before step 7: the gates show their options alone
    }
  }

  private async answer(api: Api, question: string, body: { option: string; text?: string }): Promise<void> {
    try {
      await api.post(`questions/${question}/answer`, body);
    } catch (error) {
      this.presenter.warn(error instanceof Error ? error.message : String(error));
    }
  }

  private key(file: string): string {
    const slashed = file.replace(/\\/g, "/");
    return this.caseless ? slashed.toLowerCase() : slashed;
  }
}
