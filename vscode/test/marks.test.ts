// Design 0008 §6: the annotator's marks are numbered as they are drawn, kept in the image's pixels, undone and redone
// (a clear too), dropped when too small to be meant; each is drawn at any scale with its number in a badge; a note is a
// bubble tied to its pin, its words wrapped inside it, kept on the figure wherever it is put, moved without moving its
// pin, edited (emptied, it goes and the marks after it are numbered again) and found by a click; and a send says where
// it went, with or without the marked-up figure.

import assert from "node:assert/strict";
import * as path from "node:path";
import { test } from "node:test";

import { annotate, sentLine } from "../src/core/annotate";
import type { Api } from "../src/core/controller";
import type { ServerEvent } from "../src/core/events";

interface Mark {
  n: number;
  kind: string;
  color: string;
  points: number[][];
  text?: string;
  bubble?: number[];
}

interface NoteShape {
  size: number;
  lines: string[];
  box: number[];
  anchor: number[];
}

type Measure = (text: string, size: number) => number;

interface MarksApi {
  PALETTE: string[];
  Marks: new () => {
    list: Mark[];
    past: Mark[][];
    future: Mark[][];
    count: number;
    add(kind: string, color: string, points: number[][], text?: string): Mark;
    undo(): boolean;
    redo(): boolean;
    clear(): void;
    reset(): void;
    toJSON(): Mark[];
    moveNote(n: number, at: number[]): void;
    editNote(n: number, text: string): void;
  };
  wrap(text: string, width: number, measure: (text: string) => number): string[];
  noteLayout(mark: Mark, measure: Measure, imageWidth: number, imageHeight: number): NoteShape;
  hitNote(list: Mark[], point: number[], measure: Measure, imageWidth: number, imageHeight: number): Mark | undefined;
  tooSmall(mark: Mark, slack: number): boolean;
  arrowHead(tail: number[], tip: number[], size: number): number[][];
  draw(context: unknown, mark: Mark, scale: number, imageWidth: number, imageHeight?: number): void;
}

const marks = require(path.join(__dirname, "..", "..", "media", "marks.js")) as MarksApi;

/** A 2D context that records what is drawn on it. */
function recorder(): { calls: string[]; context: Record<string, unknown> } {
  const calls: string[] = [];
  const context: Record<string, unknown> = {};
  for (const name of ["save", "restore", "beginPath", "moveTo", "lineTo", "stroke", "fill", "closePath", "arc",
    "ellipse", "strokeRect", "fillRect", "fillText", "arcTo"]) {
    context[name] = (...args: unknown[]) => calls.push(`${name}(${args.map((arg) => typeof arg === "number" ? Math.round(arg) : arg).join(",")})`);
  }
  context["measureText"] = (text: string) => ({ width: text.length * 8 });
  return { calls, context };
}

test("marks are numbered as they are drawn, and undo, redo and clear step through them", () => {
  const drawn = new marks.Marks();
  const red = marks.PALETTE[0]!;
  drawn.add("box", red, [[10.04, 20], [50, 60]]);
  drawn.add("text", red, [[5, 5]], "too crowded");
  assert.deepEqual(drawn.toJSON(), [
    { n: 1, kind: "box", color: "#e5484d", points: [[10, 20], [50, 60]] },
    { n: 2, kind: "text", color: "#e5484d", points: [[5, 5]], text: "too crowded" },
  ]);
  drawn.clear();
  assert.equal(drawn.count, 0);
  assert.ok(drawn.undo(), "a clear is undone");
  assert.equal(drawn.count, 2);
  assert.ok(drawn.undo());
  assert.equal(drawn.count, 1);
  assert.equal(drawn.add("arrow", red, [[0, 0], [30, 30]]).n, 2, "numbers follow what is shown");
  assert.equal(drawn.redo(), false, "drawing anew forgets what was undone");
  drawn.reset();
  assert.deepEqual([drawn.count, drawn.past.length, drawn.undo()], [0, 0, false]);
});

test("a mark too small to be meant is dropped, and an arrow's head is at its tip", () => {
  const click = { n: 1, kind: "box", color: "#e5484d", points: [[10, 10], [12, 13]] };
  assert.equal(marks.tooSmall(click, 6), true);
  assert.equal(marks.tooSmall({ ...click, points: [[10, 10], [40, 13]] }, 6), false);
  assert.equal(marks.tooSmall({ n: 1, kind: "text", color: "#e5484d", points: [[1, 1]], text: "" }, 6), true);
  const [one, two] = marks.arrowHead([0, 0], [100, 0], 10);
  assert.ok(one![0]! < 100 && two![0]! < 100, "behind the tip");
  assert.equal(Math.round(one![1]!), -Math.round(two![1]!), "on both sides of the shaft");
});

test("a mark is drawn at the scale shown, with its number in a badge", () => {
  const { calls, context } = recorder();
  marks.draw(context, { n: 3, kind: "box", color: "#3e63dd", points: [[100, 50], [300, 150]] }, 0.5, 640);
  assert.ok(calls.includes("strokeRect(50,25,100,50)"), calls.join(" "));
  assert.ok(calls.some((call) => call.startsWith("fillText(3,")), "the number");
});

/** Text as wide as half its size a character: what a sans-serif font is, about. */
const measure: Measure = (text, size) => text.length * size * 0.5;
const WIDE = "Mark 1: add an inset that zooms on this crossing, with a dashed vertical line at your estimate of p_c.";

function inside(box: number[], width: number, height: number): boolean {
  return box[0]! >= 0 && box[1]! >= 0 && box[2]! <= width && box[3]! <= height;
}

test("a note's words wrap inside its bubble, which stays on the figure, beside its pin", () => {
  for (const anchor of [[700, 20], [20, 20], [740, 560], [375, 285]]) {
    const shape = marks.noteLayout({ n: 1, kind: "text", color: "#e5484d", points: [anchor], text: WIDE }, measure, 750, 570);
    assert.ok(shape.lines.length > 1, "a long note takes several lines");
    assert.equal(shape.lines.join(" "), WIDE, "every word, in order");
    assert.ok(inside(shape.box, 750, 570), `nothing runs off the figure: ${shape.box} for a pin at ${anchor}`);
    const [left, top, right, bottom] = shape.box;
    assert.ok(!(anchor[0]! >= left! && anchor[0]! <= right! && anchor[1]! >= top! && anchor[1]! <= bottom!), "the pin shows");
  }
  assert.deepEqual(marks.wrap("a supercalifragilistic word", 40, (text) => text.length * 5), ["a", "supercal", "ifragili", "stic", "word"]);
  assert.deepEqual(marks.wrap("two\nlines", 400, (text) => text.length * 5), ["two", "lines"], "its own line breaks kept");
});

test("a note's bubble moves without its pin, is kept on the figure, and the move is undone", () => {
  const drawn = new marks.Marks();
  drawn.add("text", "#e5484d", [[300, 200]], "too crowded");
  drawn.moveNote(1, [40, 400]);
  const [moved] = drawn.toJSON();
  assert.deepEqual([moved!.points, moved!.bubble], [[[300, 200]], [40, 400]]);
  const far = marks.noteLayout({ ...moved!, bubble: [5000, -300] }, measure, 750, 570);
  assert.ok(inside(far.box, 750, 570), "dragged off the edge, it stays on");
  assert.deepEqual(far.anchor, [300, 200]);
  assert.ok(drawn.undo());
  assert.equal(drawn.toJSON()[0]!.bubble, undefined);
});

test("a note edited takes the new words; emptied, it goes and the marks after it are numbered again", () => {
  const drawn = new marks.Marks();
  drawn.add("box", "#e5484d", [[0, 0], [50, 50]]);
  drawn.add("text", "#3e63dd", [[100, 100]], "first words");
  drawn.add("arrow", "#e5484d", [[0, 0], [90, 90]]);
  drawn.editNote(2, "  better words ");
  assert.equal(drawn.toJSON()[1]!.text, "better words");
  drawn.editNote(2, " ");
  assert.deepEqual(drawn.toJSON().map((mark) => [mark.n, mark.kind]), [[1, "box"], [2, "arrow"]]);
});

test("a click on a note's bubble finds the note; a click beside it does not", () => {
  const list: Mark[] = [
    { n: 1, kind: "box", color: "#e5484d", points: [[0, 0], [700, 500]] },
    { n: 2, kind: "text", color: "#e5484d", points: [[300, 300]], text: "look here", bubble: [400, 100] },
  ];
  const shape = marks.noteLayout(list[1]!, measure, 750, 570);
  const middle = [(shape.box[0]! + shape.box[2]!) / 2, (shape.box[1]! + shape.box[3]!) / 2];
  assert.equal(marks.hitNote(list, middle, measure, 750, 570)?.n, 2);
  assert.equal(marks.hitNote(list, [300, 300], measure, 750, 570), undefined, "its pin is not its bubble");
});

test("a note is drawn as a bubble tied to its pin, a line for each of its lines", () => {
  const { calls, context } = recorder();
  marks.draw(context, { n: 2, kind: "text", color: "#e5484d", points: [[375, 285]], text: WIDE }, 1, 750, 570);
  assert.ok(calls.some((call) => call.startsWith("arcTo(")), "a rounded bubble");
  assert.ok(calls.filter((call) => call.startsWith("fillText(")).length >= 3, "its lines and the pin's number");
  assert.ok(calls.some((call) => call.startsWith("fillText(2,")), "the pin's number");
});

test("a send says where it went, with or without the marked-up figure", async () => {
  const sent = { workspace: "myproject", port: 4096, session: "ses_1", annotation: ".clank/annotations/p-1.png", text: "", attached: true };
  assert.equal(sentLine(sent), "Sent to the agent of myproject, with the marked-up figure.");
  assert.match(sentLine({ ...sent, attached: false }), /the marks in words \(its model reads no images\)/);
  const posts: Array<{ path: string; body: unknown }> = [];
  const api: Api = {
    get: async <T>() => ({}) as T,
    post: async <T>(where: string, body?: unknown) => {
      posts.push({ path: where, body });
      if ((body as { message: string }).message === "refuse") {
        throw new Error("no agent runs in myproject: start it");
      }
      return sent as T;
    },
    events: async function* (): AsyncGenerator<ServerEvent> {},
  };
  const annotation = { folder: "C:\\Work\\MyProject", figure: "C:\\Work\\MyProject\\figs\\a.png", marks: [], message: "bigger", image: "data:image/png;base64,AA" };
  assert.deepEqual(await annotate(api, annotation), { ok: true, text: "Sent to the agent of myproject, with the marked-up figure." });
  assert.equal(posts[0]?.path, "agents/annotations");
  assert.deepEqual(await annotate(api, { ...annotation, message: "refuse" }), { ok: false, text: "no agent runs in myproject: start it" });
});
