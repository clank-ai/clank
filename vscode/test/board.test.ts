// Design 0022 §2-§3 and §6: the board editor's pure core. A board is read from its file and written back in the same shape;
// an item inside a frame moves with the frame, and the owner's pen strokes, highlights and pins over an item move with
// the item; a move snaps the moved box's edges or center to another item's (within a few pixels) or else to the grid,
// and says the guide it snapped to; a figure resized keeps its aspect; a selection aligns, takes one width, or spreads
// evenly; new items get the next id and their kind's size; edits are operations (set, add, remove) applied in order;
// what the owner selects is named for the agent by id and what it shows; and a compiled LaTeX item's drawing is asked
// for once per source, keeping its last drawing while its source does not build.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  align,
  type Board,
  type BoardItem,
  applyOps,
  askMessage,
  Drawings,
  fillMessage,
  overWords,
  pinsMessage,
  movers,
  moveOps,
  newItem,
  parseBoard,
  resize,
  serializeBoard,
  snapMove,
} from "../src/core/board";

const BOARD: Board = {
  board: 1,
  title: "Fig 3",
  settings: { grid: 20, preamble: "" },
  items: [
    { id: "frame-5", kind: "frame", x: 60, y: 40, w: 760, h: 480, name: "Figure 3" },
    { id: "fig-1", kind: "figure", x: 80, y: 80, w: 360, h: 298, file: "figures/amp.png", caption: "(a) Amplitude" },
    { id: "latex-2", kind: "latex", x: 80, y: 420, w: 290, h: 80, source: "A(f) = \\frac{F_0}{x}", mode: "math" },
    { id: "slot-3", kind: "slot", x: 480, y: 80, w: 320, h: 220, label: "phase", state: "open" },
    { id: "note-4", kind: "note", x: 900, y: 80, w: 280, h: 120, text: "Why Q is about 25" },
    { id: "pen-6", kind: "pen", points: [[230, 100], [290, 110], [260, 150]] },
    { id: "pin-7", kind: "pin", x: 400, y: 300, text: "Mark Q", open: true },
    { id: "arrow-8", kind: "arrow", from: { item: "note-4" }, to: { item: "fig-1" } },
  ],
};

function item(id: string): BoardItem {
  return BOARD.items.find((each) => each.id === id)!;
}

test("a board is read from its file and written back in the same shape", () => {
  const text = serializeBoard(BOARD);
  assert.deepEqual(parseBoard(text), BOARD);
  assert.ok(text.endsWith("}\n"));
  assert.throws(() => parseBoard("{\"title\": 1}"), /not a board/);
});

test("what moves together: a frame takes what it holds, an item takes the marks over it", () => {
  assert.deepEqual(movers(BOARD, ["fig-1"]).sort(), ["fig-1", "pen-6", "pin-7"]);
  assert.deepEqual(movers(BOARD, ["frame-5"]).sort(), ["fig-1", "frame-5", "latex-2", "pen-6", "pin-7", "slot-3"]);
  assert.deepEqual(movers(BOARD, ["note-4"]), ["note-4"], "an arrow follows its items by id, not by moving");
  const ops = moveOps(BOARD, ["fig-1"], 20, 40);
  const moved = applyOps(BOARD, ops);
  assert.deepEqual([moved.items[1].x, moved.items[1].y], [100, 120]);
  assert.deepEqual(moved.items[5].points, [[250, 140], [310, 150], [280, 190]], "the pen stroke moved with it");
  assert.deepEqual([moved.items[6].x, moved.items[6].y], [420, 340]);
});

test("a move snaps to another item's edge or center within a few pixels, else to the grid", () => {
  const near = snapMove(BOARD, ["note-4"], 0, 3, 1);
  assert.deepEqual([near.dx, near.dy], [0, 0], "its top snapped back to the slot's top at 80");
  assert.ok(near.guides.some((guide) => guide.axis === "y" && guide.at === 80));
  const free = snapMove(BOARD, ["note-4"], 7, 33, 1);
  assert.deepEqual([free.dx, free.dy], [0, 40], "nothing near: the grid");
  const zoomed = snapMove(BOARD, ["note-4"], 0, 5, 4);
  assert.deepEqual([zoomed.dx, zoomed.dy], [0, 5], "zoomed in, the snap's reach shrinks and the grid step is 1/4");
});

test("a figure resized keeps its aspect; other items take the handle's way; nothing goes under its least size", () => {
  assert.deepEqual(resize(item("fig-1"), "se", 36, 0), { x: 80, y: 80, w: 396, h: 328 });
  assert.deepEqual(resize(item("note-4"), "e", 40, 0), { x: 900, y: 80, w: 320, h: 120 });
  assert.deepEqual(resize(item("note-4"), "nw", 20, 30), { x: 920, y: 110, w: 260, h: 90 });
  assert.deepEqual(resize(item("note-4"), "w", 400, 0), { x: 1148, y: 80, w: 32, h: 120 });
});

test("a selection aligns its edges or centers, takes one width, or spreads evenly", () => {
  const three = ["fig-1", "slot-3", "note-4"];
  const left = applyOps(BOARD, align(BOARD, three, "top"));
  assert.deepEqual(three.map((id) => left.items.find((each) => each.id === id)!.y), [80, 80, 80]);
  const widths = applyOps(BOARD, align(BOARD, ["fig-1", "latex-2"], "width"));
  assert.equal(widths.items[2].w, 360, "the widest's width");
  const spread = applyOps(BOARD, align(BOARD, three, "spread"));
  const xs = three.map((id) => spread.items.find((each) => each.id === id)!);
  const gap = (i: number): number => Number(xs[i + 1].x) - (Number(xs[i].x) + Number(xs[i].w));
  assert.equal(gap(0), gap(1), "equal gaps");
});

test("a new item gets the next id and its kind's size; edits apply in order", () => {
  const note = newItem(BOARD, "note", 100, 600);
  assert.deepEqual([note.id, note.w, note.h, note.text], ["note-9", 280, 120, ""]);
  const pen = newItem(BOARD, "pen", 0, 0, { points: [[0, 0], [10, 10]] });
  assert.equal(pen.id, "pen-9");
  const changed = applyOps(BOARD, [
    { op: "add", item: note },
    { op: "set", id: "note-9", fields: { text: "Check the decay" } },
    { op: "remove", ids: ["pin-7"] },
  ]);
  assert.equal(changed.items.at(-1)!.text, "Check the decay");
  assert.ok(!changed.items.some((each) => each.id === "pin-7"));
  assert.equal(BOARD.items.length, 8, "the board given is not changed");
  const frame = applyOps(BOARD, [{ op: "add", item: newItem(BOARD, "frame", 0, 0) }]);
  assert.equal(frame.items[0].kind, "frame", "a frame goes under what it holds");
});

test("what the owner selects is named for the agent by id and what it shows", () => {
  assert.equal(
    askMessage("figures/fig3.board", BOARD, ["fig-1", "latex-2"], "Put the equation under the plot."),
    'On the board figures/fig3.board, about fig-1 (figure figures/amp.png, "(a) Amplitude") and latex-2 ' +
      '(LaTeX "A(f) = \\frac{F_0}{x}"):\n\nPut the equation under the plot.\n\n' +
      "Read the board with board_read first, and change it with board_add, board_update and board_remove.",
  );
});

test("a slot to fill and the open pins are each a message naming what the agent works on", () => {
  assert.equal(
    fillMessage("figures/fig3.board", BOARD, "slot-3"),
    'On the board figures/fig3.board, fill the slot slot-3 ("phase"): make the figure it names from the folder\'s ' +
      'data (a script, or a job if it runs long), then place it with board_add(board="figures/fig3.board", ' +
      'kind="figure", file=..., at={"slot": "slot-3"}). It takes the slot\'s place and size.\n\n' +
      "Read the board with board_read first, and change it with board_add, board_update and board_remove.",
  );
  assert.equal(
    pinsMessage("figures/fig3.board", BOARD),
    "On the board figures/fig3.board, the owner pinned comments:\n" +
      '- pin-7, on the lower right of fig-1: "Mark Q"\n\n' +
      "Do what each asks, then close it with board_update(id=..., open=false).\n\n" +
      "Read the board with board_read first, and change it with board_add, board_update and board_remove.",
  );
  assert.equal(overWords(BOARD, 260, 125), "the upper middle of fig-1");
  assert.equal(overWords(BOARD, 2000, 2000), "the board");
});

test("a compiled drawing is asked for once per source, and a source that does not build keeps the last drawing", () => {
  const drawings = new Drawings();
  const board = (source: string): Board => ({ ...BOARD, items: [
    { id: "latex-9", kind: "latex", x: 0, y: 0, w: 300, h: 200, source, mode: "compiled" },
    { id: "latex-2", kind: "latex", x: 0, y: 0, w: 300, h: 80, source: "x", mode: "math" },
  ] });  // prettier-ignore
  const first = board("A");
  assert.deepEqual(drawings.wanted(first).map((each) => each.id), ["latex-9"], "math is drawn at once, in the page");
  assert.deepEqual(drawings.wanted(first), [], "asked once");
  assert.deepEqual(drawings.shown(first), { "latex-9": {} }, "building");
  drawings.answer(drawings.key(first, first.items[0]), { svg: "<svg>A</svg>" });
  assert.deepEqual(drawings.shown(first), { "latex-9": { svg: "<svg>A</svg>" } });
  const broken = board("A}");
  const [asked] = drawings.wanted(broken);
  drawings.answer(asked.key, { error: "Too many }'s." });
  assert.deepEqual(drawings.shown(broken), { "latex-9": { svg: "<svg>A</svg>", error: "Too many }'s." } });
  assert.deepEqual(drawings.wanted(first), [], "the first source is still drawn");
});
