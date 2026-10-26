// The board editor's pure core (design 0022 §2-§3): a board read from its file and written back in the same shape
// (`parseBoard`, `serializeBoard`), and everything the editor decides without VS Code: what moves together (`movers`:
// a frame takes what it holds, an item the owner's marks over it), a move (`moveOps`), where a move snaps
// (`snapMove`: another item's matching edge or center within a few screen pixels, else the grid), a resize (`resize`:
// a figure keeps its aspect), alignment (`align`), new items (`newItem`: the next id, the kind's size), edits as
// operations applied in order (`applyOps`), and the agent's message about a selection (`askMessage`). The page draws
// and the extension writes the file; both use these.

/** An item of a board: its id and kind, and the rest by kind (module comment of `boards.py` in the service). */
export interface BoardItem {
  id: string;
  kind: string;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  points?: number[][];
  [key: string]: unknown;
}

export interface Board {
  board: number;
  title: string;
  settings: { grid: number; preamble: string; [key: string]: unknown };
  items: BoardItem[];
}

export type Op =
  | { op: "set"; id: string; fields: Record<string, unknown> }
  | { op: "add"; item: BoardItem; index?: number }
  | { op: "remove"; ids: string[] };

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const BOXED = new Set(["figure", "latex", "note", "slot", "frame", "highlight"]);
const MARKS = new Set(["pen", "highlight", "pin"]);
const SOLID = new Set(["figure", "latex", "note", "slot"]);
const PREFIX: Record<string, string> = {
  figure: "fig", latex: "latex", note: "note", slot: "slot", frame: "frame", arrow: "arrow", pen: "pen",
  highlight: "mark", pin: "pin",
};  // prettier-ignore
const SIZES: Record<string, [number, number]> = {
  note: [280, 120], latex: [320, 80], slot: [320, 220], frame: [640, 420], highlight: [160, 60], figure: [360, 270],
};  // prettier-ignore
const REACH = 6; // screen pixels within which a move snaps to another item
const LEAST = 32; // the least width or height an item is resized to

/** A board from its file's text; an error saying why for text that is not one. */
export function parseBoard(text: string): Board {
  const found = JSON.parse(text) as Partial<Board>;
  if (!found || typeof found !== "object" || !Array.isArray(found.items)) {
    throw new Error("this file is not a board: it has no items");
  }
  return {
    ...found,
    board: found.board ?? 1,
    title: found.title ?? "",
    settings: { grid: 20, preamble: "", ...(found.settings ?? {}) },
    items: found.items,
  } as Board;
}

/** A board as its file holds it: two-space indented JSON, as the service writes it. */
export function serializeBoard(board: Board): string {
  return `${JSON.stringify(board, null, 2)}\n`;
}

export function boxOf(item: BoardItem): Box | undefined {
  if (item.kind === "pen") {
    const points = item.points ?? [];
    if (!points.length) return undefined;
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
  }
  if (item.kind === "pin") {
    return { x: item.x ?? 0, y: item.y ?? 0, w: 0, h: 0 };
  }
  if (item.x === undefined || item.y === undefined) return undefined;
  return { x: item.x, y: item.y, w: item.w ?? 0, h: item.h ?? 0 };
}

function inside(inner: Box, outer: Box): boolean {
  return outer.x <= inner.x && outer.y <= inner.y && inner.x + inner.w <= outer.x + outer.w &&
    inner.y + inner.h <= outer.y + outer.h;  // prettier-ignore
}

function centerIn(inner: Box, outer: Box): boolean {
  const cx = inner.x + inner.w / 2;
  const cy = inner.y + inner.h / 2;
  return outer.x <= cx && cx <= outer.x + outer.w && outer.y <= cy && cy <= outer.y + outer.h;
}

/** The ids that move when `ids` move: a frame takes what it holds whole (and the marks inside it), an item the owner's
 * pen strokes, highlights and pins over it. Arrows follow their items by id. */
export function movers(board: Board, ids: string[]): string[] {
  const moving = new Set(ids);
  for (const id of ids) {
    const frame = board.items.find((each) => each.id === id && each.kind === "frame");
    const area = frame && boxOf(frame);
    if (!area) continue;
    for (const each of board.items) {
      const box = boxOf(each);
      if (box && each.id !== id && ((BOXED.has(each.kind) && inside(box, area)) || (MARKS.has(each.kind) && centerIn(box, area)))) {
        moving.add(each.id);
      }
    }
  }
  for (const id of [...moving]) {
    const owner = board.items.find((each) => each.id === id);
    const area = owner && SOLID.has(owner.kind) ? boxOf(owner) : undefined;
    if (!area) continue;
    for (const each of board.items) {
      const box = boxOf(each);
      if (box && MARKS.has(each.kind) && centerIn(box, area)) {
        moving.add(each.id);
      }
    }
  }
  return [...moving];
}

/** The operations that move `ids` (and what moves with them) by `dx`, `dy`. */
export function moveOps(board: Board, ids: string[], dx: number, dy: number): Op[] {
  const ops: Op[] = [];
  for (const id of movers(board, ids)) {
    const item = board.items.find((each) => each.id === id);
    if (!item) continue;
    if (item.kind === "pen") {
      ops.push({ op: "set", id, fields: { points: (item.points ?? []).map(([x, y]) => [x + dx, y + dy]) } });
    } else if (item.x !== undefined && item.y !== undefined) {
      ops.push({ op: "set", id, fields: { x: item.x + dx, y: item.y + dy } });
    }
  }
  return ops;
}

export interface Snapped {
  dx: number;
  dy: number;
  guides: Array<{ axis: "x" | "y"; at: number }>;
}

/** Where a move of `ids` by `dx`, `dy` lands (module comment): within `REACH` screen pixels of another item's matching
 * edge or center it snaps there, else to the grid (whose step shrinks as the board is zoomed in). */
export function snapMove(board: Board, ids: string[], dx: number, dy: number, zoom: number): Snapped {
  const moving = new Set(movers(board, ids));
  const boxes = board.items.filter((each) => moving.has(each.id) && BOXED.has(each.kind)).map(boxOf).filter(
    (each): each is Box => each !== undefined,
  );  // prettier-ignore
  if (!boxes.length) return { dx, dy, guides: [] };
  const left = Math.min(...boxes.map((b) => b.x));
  const top = Math.min(...boxes.map((b) => b.y));
  const right = Math.max(...boxes.map((b) => b.x + b.w));
  const bottom = Math.max(...boxes.map((b) => b.y + b.h));
  const others = board.items.filter((each) => !moving.has(each.id) && BOXED.has(each.kind)).map(boxOf).filter(
    (each): each is Box => each !== undefined,
  );  // prettier-ignore
  const reach = REACH / zoom;
  const step = Math.max(1, (board.settings.grid || 20) / Math.max(1, zoom));
  const guides: Snapped["guides"] = [];
  const axis = (start: number, end: number, delta: number, edges: (b: Box) => number[], middles: (b: Box) => number, name: "x" | "y"): number => {
    let best: { shift: number; at: number } | undefined;
    const consider = (mine: number, theirs: number[]): void => {
      for (const at of theirs) {
        const shift = at - mine;
        if (Math.abs(shift) <= reach && (!best || Math.abs(shift) < Math.abs(best.shift))) best = { shift, at };
      }
    };
    consider(start + delta, others.flatMap(edges));
    consider(end + delta, others.flatMap(edges));
    consider((start + end) / 2 + delta, others.map(middles));
    if (best) {
      guides.push({ axis: name, at: best.at });
      return delta + best.shift;
    }
    return Math.round((start + delta) / step) * step - start;
  };  // prettier-ignore
  const sx = axis(left, right, dx, (b) => [b.x, b.x + b.w], (b) => b.x + b.w / 2, "x");
  const sy = axis(top, bottom, dy, (b) => [b.y, b.y + b.h], (b) => b.y + b.h / 2, "y");
  return { dx: sx, dy: sy, guides };
}

/** An item's box resized by a handle (n, s, e, w and their corners) moved by `dx`, `dy`: a figure keeps its aspect,
 * and nothing goes under `LEAST`, the far edge staying where it was. */
export function resize(item: BoardItem, handle: string, dx: number, dy: number): Box {
  const box = boxOf(item) ?? { x: 0, y: 0, w: LEAST, h: LEAST };
  let { x, y, w, h } = box;
  if (handle.includes("e")) w = box.w + dx;
  if (handle.includes("s")) h = box.h + dy;
  if (handle.includes("w")) w = box.w - dx;
  if (handle.includes("n")) h = box.h - dy;
  w = Math.max(LEAST, w);
  h = Math.max(LEAST, h);
  if (item.kind === "figure" && box.w > 0 && box.h > 0) {
    const aspect = box.w / box.h;
    if (handle === "n" || handle === "s") w = h * aspect;
    else h = w / aspect;
    w = Math.round(w);
    h = Math.round(h);
  }
  if (handle.includes("w")) x = box.x + box.w - w;
  if (handle.includes("n")) y = box.y + box.h - h;
  return { x, y, w, h };
}

/** Align a selection: `left`, `center`, `right`, `top`, `middle`, `bottom`; `width` and `height` (the largest's, a
 * figure keeping its aspect); `spread` (even gaps across, from the leftmost to the rightmost). */
export function align(board: Board, ids: string[], how: string): Op[] {
  const chosen = board.items.filter((each) => ids.includes(each.id) && BOXED.has(each.kind) && boxOf(each));
  if (chosen.length < 2) return [];
  const boxes = chosen.map((each) => boxOf(each)!);
  const left = Math.min(...boxes.map((b) => b.x));
  const right = Math.max(...boxes.map((b) => b.x + b.w));
  const top = Math.min(...boxes.map((b) => b.y));
  const bottom = Math.max(...boxes.map((b) => b.y + b.h));
  const set = (each: BoardItem, fields: Record<string, unknown>): Op => ({ op: "set", id: each.id, fields });
  switch (how) {
    case "left": return chosen.map((each) => set(each, { x: left }));
    case "right": return chosen.map((each, i) => set(each, { x: right - boxes[i].w }));
    case "center": return chosen.map((each, i) => set(each, { x: Math.round((left + right) / 2 - boxes[i].w / 2) }));
    case "top": return chosen.map((each) => set(each, { y: top }));
    case "bottom": return chosen.map((each, i) => set(each, { y: bottom - boxes[i].h }));
    case "middle": return chosen.map((each, i) => set(each, { y: Math.round((top + bottom) / 2 - boxes[i].h / 2) }));
    case "width": {
      const widest = Math.max(...boxes.map((b) => b.w));
      return chosen.map((each, i) => set(each, each.kind === "figure"
        ? { w: widest, h: Math.round(boxes[i].h * widest / boxes[i].w) } : { w: widest }));
    }
    case "height": {
      const tallest = Math.max(...boxes.map((b) => b.h));
      return chosen.map((each, i) => set(each, each.kind === "figure"
        ? { h: tallest, w: Math.round(boxes[i].w * tallest / boxes[i].h) } : { h: tallest }));
    }
    case "spread": {
      const order = chosen.map((each, i) => ({ each, box: boxes[i] })).sort((a, b) => a.box.x - b.box.x);
      const gap = (right - left - order.reduce((sum, one) => sum + one.box.w, 0)) / (order.length - 1);
      let at = left;
      return order.map(({ each, box }) => {
        const op = set(each, { x: Math.round(at) });
        at += box.w + gap;
        return op;
      });
    }
    default: return [];
  }  // prettier-ignore
}

/** A new item of a kind at a place, with the next id (one more than the highest number on the board) and its kind's
 * size; `extra` gives its other fields (a figure's file and size, a pen's points). */
export function newItem(board: Board, kind: string, x: number, y: number, extra: Record<string, unknown> = {}): BoardItem {
  const number = 1 + Math.max(0, ...board.items.map((each) => Number(/-(\d+)$/.exec(each.id)?.[1] ?? 0)));
  const id = `${PREFIX[kind] ?? kind}-${number}`;
  const [w, h] = SIZES[kind] ?? [0, 0];
  const defaults: Record<string, Record<string, unknown>> = {
    note: { text: "" }, latex: { source: "", mode: "math" }, slot: { label: "a figure", state: "open" },
    frame: { name: "Frame" }, pin: { text: "", open: true },
  };  // prettier-ignore
  const placed = kind === "pen" || kind === "arrow" ? {} : kind === "pin" ? { x, y } : { x, y, w, h };
  return { id, kind, ...placed, ...(defaults[kind] ?? {}), ...extra, by: "owner" };
}

/** The board after the operations, in order; the board given is left as it was. A frame added goes under the rest. */
export function applyOps(board: Board, ops: Op[]): Board {
  let items = board.items.map((each) => ({ ...each }));
  for (const op of ops) {
    if (op.op === "set") {
      items = items.map((each) => (each.id === op.id ? { ...each, ...op.fields } : each));
    } else if (op.op === "add") {
      const index = op.index ?? (op.item.kind === "frame" ? 0 : items.length);
      items.splice(index, 0, { ...op.item });
    } else {
      items = items.filter((each) => !op.ids.includes(each.id));
    }
  }
  return { ...board, items };
}

function said(item: BoardItem): string {
  const text = (value: unknown): string => String(value ?? "").split("\n")[0].slice(0, 80);
  switch (item.kind) {
    case "figure": return `figure ${text(item.file)}${item.caption ? `, "${text(item.caption)}"` : ""}`;
    case "latex": return `LaTeX "${text(item.source)}"`;
    case "note": return `note "${text(item.text)}"`;
    case "slot": return `slot "${text(item.label)}"`;
    case "frame": return `frame "${text(item.name)}"`;
    case "pin": return `pin "${text(item.text)}"`;
    default: return item.kind;
  }  // prettier-ignore
}

/** The items named for the agent: each id with what it shows, the last two joined by "and". */
export function namedItems(board: Board, ids: string[]): string {
  const named = ids.map((id) => board.items.find((each) => each.id === id)).filter((each): each is BoardItem => !!each)
    .map((each) => `${each.id} (${said(each)})`);  // prettier-ignore
  return named.length <= 1 ? (named[0] ?? "") : `${named.slice(0, -1).join(", ")} and ${named.at(-1)}`;
}

const TOOLS_SAID = "Read the board with board_read first, and change it with board_add, board_update and board_remove.";

/** The message the owner's selection and words make for the agent. */
export function askMessage(path: string, board: Board, ids: string[], text: string): string {
  return `On the board ${path}, about ${namedItems(board, ids)}:\n\n${text.trim()}\n\n${TOOLS_SAID}`;
}

/** Where a point is on the board, in words: on the upper left ... center ... lower right of the topmost item there
 * (frames aside), as the service says it to the model; else "the board". */
export function overWords(board: Board, x: number, y: number): string {
  for (const item of [...board.items].reverse()) {
    const box = SOLID.has(item.kind) ? boxOf(item) : undefined;
    if (!box || x < box.x || x > box.x + box.w || y < box.y || y > box.y + box.h) continue;
    const across = (x - box.x) / Math.max(box.w, 1);
    const down = (y - box.y) / Math.max(box.h, 1);
    const row = down < 1 / 3 ? "upper" : down > 2 / 3 ? "lower" : "middle";
    const column = across < 1 / 3 ? "left" : across > 2 / 3 ? "right" : "middle";
    return `the ${row === "middle" && column === "middle" ? "center" : `${row} ${column}`} of ${item.id}`;
  }
  return "the board";
}

/** The message that asks the agent to fill a slot the owner drew. */
export function fillMessage(path: string, board: Board, id: string): string {
  const slot = board.items.find((each) => each.id === id);
  return `On the board ${path}, fill the slot ${id} ("${String(slot?.label ?? "a figure")}"): make the figure it names ` +
    `from the folder's data (a script, or a job if it runs long), then place it with board_add(board="${path}", ` +
    `kind="figure", file=..., at={"slot": "${id}"}). It takes the slot's place and size.\n\n${TOOLS_SAID}`;  // prettier-ignore
}

/** The message that sends the agent every open pin, each by what it is on. */
export function pinsMessage(path: string, board: Board): string {
  const pins = board.items.filter((each) => each.kind === "pin" && each.open !== false);
  const lines = pins.map((pin) => `- ${pin.id}, on ${overWords(board, pin.x ?? 0, pin.y ?? 0)}: "${String(pin.text ?? "")}"`);
  return `On the board ${path}, the owner pinned comments:\n${lines.join("\n")}\n\n` +
    `Do what each asks, then close it with board_update(id=..., open=false).\n\n${TOOLS_SAID}`;  // prettier-ignore
}
