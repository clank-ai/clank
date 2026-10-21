// What the extension shows, as last read: the service, Docker, the questions waiting, and the runtime's slots and
// presets (design 0002 §1: clients hold no state of their own; this is a copy, read from the API and kept current by
// the event stream). `touched` says which topics an event changes, so the controller reads those again.

import type { Preset, Question, SlotRecord } from "./kinds";

/** The service, as `GET /api/v1/service` says. */
export interface ServiceInfo {
  version: string;
  url: string;
  started: string;
  clients: string[];
}

/** A container, as `GET /api/v1/docker` lists it. */
export interface ContainerInfo {
  name: string;
  state: string;
  owner: "clank" | "other";
}

/** Docker, as `GET /api/v1/docker` says. */
export interface DockerInfo {
  label: string;
  state: string;
  version: string;
  engine: string;
  summary: string;
  detail: string;
  containers: ContainerInfo[];
}

/** A preset, as `GET /api/v1/runtime/presets` lists it: its record, its id, where its file is, and why it cannot run;
 * a cloud preset (design 0016 §7) its provider, its endpoint and its price in the service's words. */
export interface PresetView extends Preset {
  id: string;
  source: string;
  file: string;
  problems: string[];
  provider?: string;
  price_said?: string;
}

/** The cloud's cost as `GET /api/v1/gateway/cost` gives it: the extension shows its words (design 0016 §11). */
export interface CostView {
  said: string;
  paused: { said: string } | null;
}

/** Everything the extension shows. */
export class State {
  connected = false;
  service: ServiceInfo | undefined = undefined;
  docker: DockerInfo | undefined = undefined;
  questions: Question[] = [];
  slots: SlotRecord[] = [];
  presets: PresetView[] = [];
  cost: CostView | undefined = undefined;
  lastEvent: number | undefined = undefined;
}

/** What the extension reads again when an event touches it. */
export type Topic = "questions" | "docker" | "service" | "slots" | "presets" | "cost";

/** The topics an event of this type changes (a settings event's by the kind of record it is about). */
export function touched(type: string, subject?: string): Topic[] {
  if (type.startsWith("question.")) {
    return ["questions"];
  }
  if (type === "docker.changed") {
    return ["docker"];
  }
  if (type.startsWith("service.")) {
    return ["service"];
  }
  if (type === "runtime.slot") {
    return ["slots"];
  }
  if (type.startsWith("settings.") && subject === "preset") {
    return ["presets"];
  }
  if (type === "gateway.cost" || type.startsWith("gateway.limit_")) {
    return ["cost"];
  }
  return [];
}
