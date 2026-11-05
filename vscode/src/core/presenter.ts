// What the controller asks of VS Code, and nothing more: the two status bar items, a question shown with its options,
// a pick from a list, a box to type an answer in, and the files the agent opened for the owner (design 0018 §7). `extension.ts` implements it with VS Code's API; the tests with a fake, so the
// controller is tested without VS Code.

import type { ArtifactMade } from "./artifacts";
import type { Question } from "./kinds";
import type { Shown } from "./show";

/** One item of a pick: what it shows, and what choosing it gives. */
export interface Choice<T> {
  label: string;
  detail?: string;
  value: T;
}

/** VS Code, as the controller sees it. */
export interface Presenter {
  /** The Clank item of the status bar: its text and its tooltip. */
  clank(text: string, tooltip: string): void;
  /** The Docker item of the status bar: its text and its tooltip. */
  docker(text: string, tooltip: string): void;
  /** Show a question with its options; the id of the option chosen, or undefined when it was dismissed. */
  ask(question: Question): Promise<string | undefined>;
  /** Let the user pick one of these; undefined when the pick was dismissed. */
  pick<T>(items: Array<Choice<T>>, placeholder: string): Promise<T | undefined>;
  /** Let the user type an answer, `prompt` saying what, `problem` what is wrong with a text as typed (undefined: nothing,
   * it may be sent); the text, or undefined when the box was dismissed. */
  input(prompt: string, problem: (text: string) => string | undefined): Promise<string | undefined>;
  /** Say something. */
  info(text: string): void;
  /** Say something went wrong, in the service's own words when it refused. */
  warn(text: string): void;
  /** Open the files the agent opened for the owner, when this window is on their folder (design 0018 §7.2). */
  showFiles?(shown: Shown): Promise<void>;
  /** An artifact the agent made (design 0021 §5): opened in a window on its folder, beside the files. */
  openArtifact?(made: ArtifactMade): Promise<void>;
}
