// What the extension does (design 0002 §2.5, §2.7, §3.2): it connects to the Clank service and keeps the status bar
// current (the service and the questions waiting, Docker's state); a question asked while VS Code is open, or one
// already waiting when it connects, is shown once with its options and answered with the one chosen, and one picked
// from the list is answered the same way; Docker is started and stopped through operations, each with a request key;
// typing tells the service the user is here, at most once a minute. The Clank item also shows what the main slot runs
// (design 0003 §8.3), its state and why in the tooltip; Switch model picks a preset and switches the main slot, and a
// click on the item answers the questions when some wait, else switches the model. Without a service it says so and
// tries again every few seconds. It speaks to VS Code only through a `Presenter`, and holds nothing of its own beyond the copy in
// `State`. A question about a change the agent asks for goes to the review (`review.ts`, design 0007) when there is one,
// with the events, instead of a notification. Completion (`completion.ts`, design 0006 §5) reads its settings and its
// slot when it connects and when they change. The Notion review (`notion.ts`, design 0010 §6) reads the batches waiting
// when it connects and follows their events; its view and its page act through `notion`. A question about a flow (a
// gate, design 0013 §10) goes to the gates (`gates.ts`): a notification with its answers, Open and Diff. When a flow's
// box switched the main slot, the window is told its model changed, in the service's words (design 0013 §7). With a
// cloud model in the main slot (design 0016 §17), the Clank item says "cloud", its tooltip the cloud's spending today
// and this month and a pause, all in the service's words; Switch model lists a cloud preset as its provider and model
// with its price as the service says it. A service without the cloud's routes shows none of it. The files the agent opened
// for the owner (`agents.shown`, design 0018 §7) go to the presenter, which opens them in a window on their folder.

import { type Annotation, annotate } from "./annotate";
import { ClankError, NotRunning } from "./client";
import type { Completer } from "./completion";
import type { ServerEvent } from "./events";
import { aboutFlow, type Gates } from "./gates";
import type { Question, SlotRecord } from "./kinds";
import type { NotionReviews } from "./notion";
import type { Presenter } from "./presenter";
import { markedUp, shown } from "./show";
import { aboutChange, type Reviews } from "./review";
import { type CostView, type DockerInfo, type PresetView, type ServiceInfo, State, touched } from "./state";

const PRESENCE_MS = 60_000;

/** The API, as the controller uses it (`ClankClient` is one). */
export interface Api {
  get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T>;
  post<T>(path: string, body?: unknown, requestKey?: string): Promise<T>;
  /** DELETE (optional: only the Notion review takes something back). */
  delete?<T>(path: string): Promise<T>;
  events(after: number | undefined, signal: AbortSignal): AsyncGenerator<ServerEvent>;
}

/** How the controller runs: where CLANK_HOME is (for what it says), how often it tries again, its clock and keys. */
export interface Options {
  home: string;
  retryMs?: number;
  now?: () => number;
  newKey?: () => string;
  reviews?: Reviews;
  completion?: Completer;
  notion?: NotionReviews;
  gates?: Gates;
  /** The workspace of the window's folder, when known (the readout's): its jobs' ends are said (design 0021 §6). */
  workspace?: () => string | undefined;
}

interface EventData {
  id?: number;
  type?: string;
  summary?: string;
  subject?: { kind?: string; id?: string } | null;
  data?: { clients?: string[]; workspace?: string; job?: number };
}

const PATHS = {
  questions: "questions",
  docker: "docker",
  service: "service",
  slots: "runtime/slots",
  presets: "runtime/presets",
  cost: "gateway/cost",
} as const;

/** The extension's behavior, behind its presenter. */
export class Controller {
  readonly state = new State();
  private stopped = false;
  private running: AbortController | undefined;
  private wakeUp: (() => void) | undefined;
  private presence: number | undefined;
  private readonly shown = new Set<string>();
  private readonly retryMs: number;
  private readonly now: () => number;
  private readonly newKey: () => string;

  constructor(
    private readonly presenter: Presenter,
    private readonly connect: () => Api | undefined,
    private readonly options: Options,
  ) {
    this.retryMs = options.retryMs ?? 3000;
    this.now = options.now ?? Date.now;
    this.newKey = options.newKey ?? (() => `vscode-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  }

  /** Connect, and keep following the service until stopped. */
  start(): void {
    this.draw();
    void this.loop();
  }

  /** Stop following the service. */
  stop(): void {
    this.stopped = true;
    this.running?.abort();
    this.wakeUp?.();
  }

  /** Connect again now (after the service was started, say). */
  reconnect(): void {
    this.running?.abort();
    this.wakeUp?.();
  }

  /** Accept a change the agent asks for (design 0007): the one named, else the one open in this window. */
  async acceptChange(question?: string): Promise<void> {
    const api = this.connect();
    if (api === undefined || this.options.reviews === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    await this.options.reviews.accept(api, question);
  }

  /** Reject a change the agent asks for, with what to tell it. */
  async rejectChange(question?: string): Promise<void> {
    const api = this.connect();
    if (api === undefined || this.options.reviews === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    await this.options.reviews.reject(api, question);
  }

  /** Switch the window's workspace between reviewing each change and auto mode. */
  async switchReview(): Promise<void> {
    const api = this.connect();
    if (api === undefined || this.options.reviews === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    await this.options.reviews.switchMode(api);
  }

  /** Do something with the Notion review (design 0010 §6): open a batch, approve, reject. */
  async notion(work: (notion: NotionReviews, api: Api) => Promise<void>): Promise<void> {
    const api = this.connect();
    if (api === undefined || this.options.notion === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    await work(this.options.notion, api);
  }

  /** Send a figure the owner marked up to the workspace's agent (design 0008); the line the annotator shows. */
  async annotate(annotation: Annotation): Promise<{ ok: boolean; text: string }> {
    const api = this.connect();
    if (api === undefined) {
      return { ok: false, text: this.notRunning() };
    }
    return annotate(api, annotation);
  }

  /** Turn completion off or on, for every window (design 0006 §5). */
  async toggleCompletion(): Promise<void> {
    const api = this.connect();
    if (api === undefined || this.options.completion === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    await this.options.completion.toggle(api);
  }

  /** Pick a waiting question, then one of its options; answer with it. */
  async questions(): Promise<void> {
    const api = this.connect();
    if (api === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    const questions = await this.read<Question[]>(api, "questions");
    if (!questions?.length) {
      this.presenter.info("No question waits for you.");
      return;
    }
    const chosen = await this.presenter.pick(
      questions.map((question) => ({ label: question.title, detail: describe(question), value: question })),
      "Which question?",
    );
    if (chosen === undefined) {
      return;
    }
    if (this.options.gates && aboutFlow(chosen)) {
      await this.options.gates.show(api, chosen); // the gate, with Open and Diff
      return;
    }
    const option = await this.presenter.pick(
      chosen.options.map((choice) => ({ label: choice.label, detail: choice.effect, value: choice.id })),
      chosen.title,
    );
    if (option !== undefined) {
      await this.answer(api, chosen, option);
    }
  }

  /** Pick a preset, and switch the main slot to it: an operation in the service (back to the last that worked if the
   * new one fails). */
  async switchModel(): Promise<void> {
    const api = this.connect();
    if (api === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    const presets = this.state.presets.length ? this.state.presets : await this.read<PresetView[]>(api, "runtime/presets");
    if (!presets?.length) {
      this.presenter.info("There is no preset to switch to.");
      return;
    }
    const chosen = await this.presenter.pick(
      presets.map((preset) => ({ label: preset.title, detail: presetLine(preset), value: preset })),
      "Switch the main slot to",
    );
    if (chosen === undefined) {
      return;
    }
    try {
      await api.post("runtime/slots/main/switch", { preset: chosen.id }, this.newKey());
      this.presenter.info(`Switching main to ${chosen.title}; the status bar follows it.`);
    } catch (error) {
      this.presenter.warn(words(error));
    }
  }

  /** The Clank item clicked: the questions when some wait, else the model switch. */
  async clicked(): Promise<void> {
    if (this.state.questions.length) {
      await this.questions();
    } else {
      await this.switchModel();
    }
  }

  /** Start or stop Docker: an operation in the service (stopping asks first when others' containers run). */
  async docker(action: "start" | "stop"): Promise<void> {
    const api = this.connect();
    if (api === undefined) {
      this.presenter.warn(this.notRunning());
      return;
    }
    try {
      await api.post(`docker/${action}`, {}, this.newKey());
      this.presenter.info(`Asked Docker to ${action}; the status bar follows it.`);
    } catch (error) {
      this.presenter.warn(words(error));
    }
  }

  /** Pick whether to start or stop Docker. */
  async chooseDocker(): Promise<void> {
    const running = this.state.docker?.state === "running";
    const choices = [
      { label: "Stop Docker", detail: "Asks first when containers Clank did not start run.", value: "stop" as const },
      { label: "Start Docker", detail: "Waits until its engine answers.", value: "start" as const },
    ];
    const action = await this.presenter.pick(running ? choices : choices.reverse(), "Docker");
    if (action !== undefined) {
      await this.docker(action);
    }
  }

  /** A file was saved: a gate it was opened from comes back (design 0013 §10: edit, then approve). */
  async saved(file: string): Promise<void> {
    const api = this.connect();
    if (api !== undefined) {
      await this.options.gates?.saved(api, file);
    }
  }

  /** The user typed: tell the service, at most once a minute (design 0002 §2.7). */
  typing(): void {
    const moment = this.now();
    if (this.presence !== undefined && moment - this.presence < PRESENCE_MS) {
      return;
    }
    this.presence = moment;
    this.connect()
      ?.post("presence")
      .catch(() => undefined);
  }

  private async loop(): Promise<void> {
    while (!this.stopped) {
      const api = this.connect();
      if (api !== undefined) {
        await this.follow(api);
      }
      this.state.connected = false;
      this.draw();
      this.options.reviews?.disconnected();
      this.options.completion?.disconnected();
      this.options.notion?.disconnected();
      if (!this.stopped) {
        await this.pause();
      }
    }
  }

  private async follow(api: Api): Promise<void> {
    this.running = new AbortController();
    try {
      await this.load(api);
      for await (const message of api.events(this.state.lastEvent, this.running.signal)) {
        if (this.stopped) {
          return;
        }
        await this.receive(api, message);
      }
    } catch (error) {
      if (!(error instanceof NotRunning) && !(error instanceof ClankError)) {
        this.presenter.warn(`Following the Clank service failed: ${words(error)}`);
      }
    }
  }

  private async load(api: Api): Promise<void> {
    const newest = await api.get<Array<{ id: number }>>("history", { limit: 1 });
    this.state.lastEvent = newest[0]?.id;
    this.state.service = await api.get<ServiceInfo>("service");
    this.state.docker = await api.get<DockerInfo>("docker");
    this.state.questions = await api.get<Question[]>("questions");
    this.state.slots = await api.get<SlotRecord[]>("runtime/slots");
    this.state.presets = await api.get<PresetView[]>("runtime/presets");
    this.state.cost = await optional<CostView>(api, "gateway/cost");
    this.state.connected = true;
    this.draw();
    await this.options.reviews?.load(api, this.state.questions);
    await this.options.completion?.load(api);
    await this.options.notion?.load(api);
    await this.options.gates?.load(api, this.state.questions);
    for (const waiting of this.state.questions) {
      if (!(this.options.reviews && aboutChange(waiting)) && !(this.options.gates && aboutFlow(waiting))) {
        this.offer(api, waiting);
      }
    }
  }

  private async receive(api: Api, message: ServerEvent): Promise<void> {
    const data = (message.data ?? {}) as EventData;
    if (message.name === "reset") {
      await this.load(api);
      return;
    }
    if (message.name === "service.clients" && this.state.service) {
      this.state.service = { ...this.state.service, clients: data.data?.clients ?? [] };
    }
    if (message.id !== undefined) {
      this.state.lastEvent = message.id;
      for (const topic of touched(message.name, data.subject?.kind)) {
        const fresh =
          topic === "cost" ? await optional<CostView>(api, PATHS[topic]) : await api.get<never>(PATHS[topic]);
        Object.assign(this.state, { [topic]: fresh });
      }
      if (message.name === "agents.model_changed" && data.summary) {
        this.presenter.info(data.summary); // a flow's box switched the main slot: the window is told (design 0013 §7)
      }
      const workspace = data.data?.workspace;
      if (message.name === "agents.job_ended" && workspace && workspace === this.options.workspace?.()) {
        const said = (data.summary ?? "").replace(`${workspace}: `, "");
        this.presenter.info(`${said}. Its log: .clank/jobs/agent/${data.data?.job}/log`); // design 0021 §6
      }
      const opened = shown(message) ?? markedUp(message); // and a LaTeX change's PDF (design 0020 §9)
      if (opened) {
        await this.presenter.showFiles?.(opened); // the agent opened files for the owner (design 0018 §7)
      }
      if (message.name === "question.asked" && data.subject?.id) {
        const asked = this.state.questions.find((question) => question.id === data.subject?.id);
        if (asked && this.options.reviews && aboutChange(asked)) {
          await this.options.reviews.offer(api, asked);
        } else if (asked && this.options.gates && aboutFlow(asked)) {
          await this.options.gates.offer(api, asked);
        } else if (asked) {
          this.offer(api, asked);
        }
      }
      await this.options.reviews?.event(api, message);
      await this.options.completion?.event(api, message);
      await this.options.notion?.event(api, message);
      await this.options.gates?.event(api, message);
    }
    this.draw();
  }

  /** Show a question as a notification, once per question however many times it is read. */
  private offer(api: Api, question: Question): void {
    if (this.shown.has(question.id)) {
      return;
    }
    this.shown.add(question.id);
    void this.notify(api, question);
  }

  private async notify(api: Api, question: Question): Promise<void> {
    const option = await this.presenter.ask(question);
    if (option !== undefined) {
      await this.answer(api, question, option);
    }
  }

  private async answer(api: Api, question: Question, option: string): Promise<void> {
    try {
      await api.post(`questions/${question.id}/answer`, { option });
    } catch (error) {
      this.presenter.warn(words(error));
    }
  }

  private async read<T>(api: Api, path: string): Promise<T | undefined> {
    try {
      return await api.get<T>(path);
    } catch (error) {
      this.presenter.warn(words(error));
      return undefined;
    }
  }

  private draw(): void {
    const { connected, service, docker, questions } = this.state;
    if (!connected || service === undefined) {
      this.presenter.clank("$(debug-disconnect) Clank: not running", this.notRunning());
      this.presenter.docker("$(package) Docker: ?", "Docker's state shows once the Clank service runs.");
      return;
    }
    const waiting = questions.length;
    const count = waiting === 1 ? "1 question" : `${waiting} questions`;
    const clients = service.clients.length ? service.clients.join(", ") : "none";
    const main = this.state.slots.find((slot) => slot.name === "main");
    const runs = main && ["starting", "ready", "stopping"].includes(main.status) ? this.title(main.preset) : undefined;
    const cloud = Boolean(this.state.presets.find((each) => each.id === main?.preset)?.endpoint);
    const state = main?.status === "ready" ? "" : ` (${main?.status})`;
    const what = runs ? ` · ${runs}${state}` + (cloud ? " · cloud" : "") : "";
    const slotLine = main ? ` main: ${main.status} since ${main.since}: ${main.reason}.` : "";
    const cost = this.state.cost;
    const paused = cost?.paused?.said;
    const costLine = cost?.said ? ` Cloud: ${cost.said}.` + (paused ? ` ${paused}: raise it in Clank.` : "") : "";
    const text = paused
      ? "$(debug-pause) Clank · cloud paused"
      : (waiting ? "$(question) Clank" : "$(server) Clank") + what + (waiting ? ` · ${count}` : "");
    this.presenter.clank(
      text,
      `Clank ${service.version} at ${service.url}, up since ${service.started}; clients following it: ${clients}.` +
        slotLine +
        costLine +
        (waiting ? ` ${count} wait for you: click to answer.` : " Click to switch the model."),
    );
    this.presenter.docker(
      `$(package) Docker: ${docker?.state ?? "?"}`,
      docker ? `${docker.summary}. Click to start or stop it.` : "Not read yet.",
    );
  }

  private title(preset: string | null): string {
    return this.state.presets.find((each) => each.id === preset)?.title ?? preset ?? "";
  }

  private notRunning(): string {
    return `The Clank service is not running for ${this.options.home}: start it with \`clank serve --background\` or \`clank console\`.`;
  }

  private pause(): Promise<void> {
    return new Promise((resolve) => {
      const timer = setTimeout(resolve, this.retryMs);
      this.wakeUp = () => {
        clearTimeout(timer);
        resolve();
      };
    });
  }
}

/** A route of the cloud's, or nothing when it cannot be read (a service without it answers 404): the status bar
 * then shows no cost, and the rest goes on. */
async function optional<T>(api: Api, path: string): Promise<T | undefined> {
  try {
    return await api.get<T>(path);
  } catch {
    return undefined;
  }
}

function presetLine(preset: PresetView): string {
  const setup = preset.endpoint
    ? `${preset.provider ?? `cloud ${preset.endpoint}`} · ${preset.model}` +
      (preset.price_said ? ` · ${preset.price_said}` : "")
    : `${preset.engine} ${preset.engine_version} · ${preset.model}`;
  return preset.problems.length ? `${setup} · cannot run: ${preset.problems.join("; ")}` : setup;
}

function describe(question: Question): string {
  const options = question.options.map((option) => option.label).join(" · ");
  return [question.detail, options].filter(Boolean).join(" — ");
}

function words(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
