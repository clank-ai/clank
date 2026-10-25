// The marks of Clank's figure annotator (design 0008 §6): what the owner draws on a figure, kept in the image's own
// pixels, numbered as they are drawn, undone and redone; how each is drawn (on the screen at any scale, and on the
// marked-up copy sent to the agent); and their numbers' badges. A note is a bubble tied to a pin: the pin (its number)
// is what the note is about, the bubble holds its words, wrapped, and is kept on the figure wherever it is put; moving
// the bubble moves only where it is shown. On a PDF's page (design 0020 §10), three more marks for text: a highlight
// (a translucent box), a strike (a line through words) and an insertion (a caret at a point, with its words as a
// note's). It is a plain script, so the page loads it as it is and Node's tests require
// it: it touches no page and no canvas of its own, only the 2D context it is given.
(function (root) {
  "use strict";

  /** The colors, red first; their names are the service's (`figures.COLORS`). */
  const PALETTE = ["#e5484d", "#3e63dd", "#30a46c", "#f5a524"];
  /** The tools: the pen draws freely; a box, a circle and an arrow are dragged; a text is placed with a click; on a
   * PDF's page, a highlight and a strike are dragged and an insertion is placed with a click, with its words. */
  const TOOLS = ["pen", "box", "circle", "arrow", "text", "highlight", "strike", "insert"];
  /** The marks that carry words in a bubble: a note, and an insertion (what to insert). */
  const WORDED = ["text", "insert"];

  /** The marks drawn, in order; each change kept, so undo and redo step through them (a clear too). */
  class Marks {
    constructor() {
      this.reset();
    }

    /** No marks and no history: after a send. */
    reset() {
      this.list = [];
      this.past = [];
      this.future = [];
    }

    /** A new mark, numbered after the last; drawing anew forgets what was undone. */
    add(kind, color, points, text) {
      const mark = { n: this.list.length + 1, kind, color, points: points.map((p) => [round(p[0]), round(p[1])]) };
      if (WORDED.includes(kind)) mark.text = String(text || "");
      this.change([...this.list, mark]);
      return mark;
    }

    undo() {
      if (!this.past.length) return false;
      this.future.push(this.list);
      this.list = this.past.pop();
      return true;
    }

    redo() {
      if (!this.future.length) return false;
      this.past.push(this.list);
      this.list = this.future.pop();
      return true;
    }

    clear() {
      if (this.list.length) this.change([]);
    }

    /** A note's bubble put elsewhere (its top left corner, in the image's pixels): its pin stays where it was. */
    moveNote(n, at) {
      const bubble = [round(at[0]), round(at[1])];
      this.change(this.list.map((mark) => (mark.n === n ? { ...mark, bubble } : mark)));
    }

    /** A note's new words; emptied, the note goes and the marks after it are numbered again. */
    editNote(n, text) {
      const words = String(text || "").trim();
      const kept = words
        ? this.list.map((mark) => (mark.n === n ? { ...mark, text: words } : mark))
        : this.list.filter((mark) => mark.n !== n).map((mark, index) => ({ ...mark, n: index + 1 }));
      this.change(kept);
    }

    change(next) {
      this.past.push(this.list);
      this.list = next;
      this.future = [];
    }

    get count() {
      return this.list.length;
    }

    /** The marks as the service takes them. */
    toJSON() {
      return this.list.map((mark) => ({ ...mark, points: mark.points.map((p) => [p[0], p[1]]) }));
    }
  }

  function round(value) {
    return Math.round(value * 10) / 10;
  }

  /** A mark's box: left, top, right, bottom. */
  function bounds(mark) {
    const xs = mark.points.map((p) => p[0]);
    const ys = mark.points.map((p) => p[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  }

  /** Whether a dragged mark is too small to be meant (a click with the box, circle or arrow tool). */
  function tooSmall(mark, slack) {
    if (WORDED.includes(mark.kind)) return !mark.text;
    const [left, top, right, bottom] = bounds(mark);
    return right - left < slack && bottom - top < slack;
  }

  /** The two sides of an arrow's head, at its tip. */
  function arrowHead(tail, tip, size) {
    const angle = Math.atan2(tip[1] - tail[1], tip[0] - tail[0]);
    const spread = Math.PI / 7;
    return [
      [tip[0] - size * Math.cos(angle - spread), tip[1] - size * Math.sin(angle - spread)],
      [tip[0] - size * Math.cos(angle + spread), tip[1] - size * Math.sin(angle + spread)],
    ];
  }

  /** Where a mark's number goes: the start of a stroke, a shape's top left corner, an arrow's tail. */
  function badgeAt(mark) {
    if (mark.kind === "box" || mark.kind === "circle" || mark.kind === "highlight") {
      const [left, top] = bounds(mark);
      return [left, top];
    }
    return mark.points[0];
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  /** A note's look for an image of this width, in the image's pixels: its font size, the bubble's padding, a line's
   * height, how far the bubble starts from its pin, and how far it stays from the figure's edges. */
  function noteLook(imageWidth) {
    const size = Math.max(13, imageWidth / 58);
    return { size, padding: size * 0.55, line: size * 1.3, gap: size * 1.4, margin: size * 0.4 };
  }

  /** Words broken into lines no wider than `width` (as `measure` measures them), the note's own line breaks kept; a
   * word wider than a line is cut where it fills one. */
  function wrap(text, width, measure) {
    const lines = [];
    for (const paragraph of String(text).split("\n")) {
      let line = "";
      for (const word of paragraph.split(/\s+/).filter(Boolean)) {
        let rest = word;
        while (measure(rest) > width && rest.length > 1) {
          let cut = rest.length - 1;
          while (cut > 1 && measure(rest.slice(0, cut)) > width) cut--;
          if (line) lines.push(line);
          line = "";
          lines.push(rest.slice(0, cut));
          rest = rest.slice(cut);
        }
        const longer = line ? `${line} ${rest}` : rest;
        if (line && measure(longer) > width) {
          lines.push(line);
          line = rest;
        } else {
          line = longer;
        }
      }
      lines.push(line);
    }
    return lines;
  }

  /** Where a note is shown, in the image's pixels: the widest its lines may be, its lines, its bubble (left, top,
   * right, bottom) and its pin. The
   * bubble is where it was put (`bubble`, its top left corner), else above and right of the pin (left of it, or below
   * it, where the figure ends); either way it is kept on the figure. `measure(text, size)` measures text at a size. */
  function noteLayout(mark, measure, imageWidth, imageHeight) {
    const look = noteLook(imageWidth);
    const tall = imageHeight === undefined ? Infinity : imageHeight;
    const room = imageWidth - 2 * (look.margin + look.padding);
    const widest = Math.max(look.size * 4, Math.min(Math.max(imageWidth * 0.34, look.size * 8), room));
    const lines = wrap(mark.text || "", widest, (text) => measure(text, look.size));
    const width = Math.max(look.size * 2, ...lines.map((line) => measure(line, look.size))) + 2 * look.padding;
    const height = lines.length * look.line + 2 * look.padding;
    const [x, y] = mark.points[0];
    let left;
    let top;
    if (mark.bubble) {
      [left, top] = mark.bubble;
    } else {
      left = x + look.gap;
      top = y - look.gap - height;
      if (left + width > imageWidth - look.margin) left = x - look.gap - width;
      if (top < look.margin) top = y + look.gap;
    }
    left = clamp(left, look.margin, imageWidth - look.margin - width);
    top = clamp(top, look.margin, tall - look.margin - height);
    return { ...look, widest, lines, box: [left, top, left + width, top + height], anchor: [x, y] };
  }

  /** The note whose bubble is at a point (the one drawn last, when bubbles overlap). */
  function hitNote(list, point, measure, imageWidth, imageHeight) {
    for (let index = list.length - 1; index >= 0; index--) {
      const mark = list[index];
      if (!WORDED.includes(mark.kind)) continue;
      const [left, top, right, bottom] = noteLayout(mark, measure, imageWidth, imageHeight).box;
      if (point[0] >= left && point[0] <= right && point[1] >= top && point[1] <= bottom) return mark;
    }
    return undefined;
  }

  /** Text measured with a 2D context at a size, in the font a note is drawn in. */
  function measurer(context) {
    return (text, size) => {
      context.font = noteFont(size);
      return context.measureText(text).width;
    };
  }

  function noteFont(size) {
    return `500 ${size}px sans-serif`;
  }

  /** A note: a thin line from its pin to the nearest point of its bubble, the bubble (white, edged in the note's
   * color, rounded), and its lines in it. */
  function drawNote(context, mark, scale, imageWidth, imageHeight) {
    const shape = noteLayout(mark, measurer(context), imageWidth, imageHeight);
    const [left, top, right, bottom] = shape.box.map((value) => value * scale);
    const [x, y] = shape.anchor.map((value) => value * scale);
    context.lineWidth = Math.max(1.5, shape.size / 9) * scale;
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(clamp(x, left, right), clamp(y, top, bottom));
    context.stroke();
    const radius = Math.min(shape.size * 0.5 * scale, (bottom - top) / 2);
    context.beginPath();
    context.moveTo(left + radius, top);
    context.arcTo(right, top, right, bottom, radius);
    context.arcTo(right, bottom, left, bottom, radius);
    context.arcTo(left, bottom, left, top, radius);
    context.arcTo(left, top, right, top, radius);
    context.closePath();
    context.save();
    context.shadowColor = "rgba(0, 0, 0, 0.28)";
    context.shadowBlur = 6 * scale;
    context.shadowOffsetY = 1.5 * scale;
    context.fillStyle = "rgba(255, 255, 255, 0.97)";
    context.fill();
    context.restore();
    context.lineWidth = Math.max(1.5, shape.size / 8) * scale;
    context.stroke();
    context.fillStyle = "#1f2328";
    context.font = noteFont(shape.size * scale);
    context.textAlign = "left";
    context.textBaseline = "middle";
    shape.lines.forEach((line, index) => {
      context.fillText(line, left + shape.padding * scale, top + (shape.padding + shape.line * (index + 0.5)) * scale);
    });
  }

  /** The width of a stroke for an image of this width (seen at `scale` screen pixels per image pixel). */
  function strokeWidth(imageWidth) {
    return Math.max(3, imageWidth / 320);
  }

  /** Draw a mark on a 2D context whose units are the image's pixels times `scale` (a note is kept inside an image of
   * this width and height). */
  function draw(context, mark, scale, imageWidth, imageHeight) {
    const width = strokeWidth(imageWidth) * scale;
    const at = (p) => [p[0] * scale, p[1] * scale];
    context.save();
    context.strokeStyle = mark.color;
    context.fillStyle = mark.color;
    context.lineWidth = width;
    context.lineCap = "round";
    context.lineJoin = "round";
    if (mark.kind === "pen") {
      context.beginPath();
      mark.points.forEach((p, index) => {
        const [x, y] = at(p);
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.stroke();
    } else if (mark.kind === "box") {
      const [left, top, right, bottom] = bounds(mark).map((value) => value * scale);
      context.strokeRect(left, top, right - left, bottom - top);
    } else if (mark.kind === "circle") {
      const [left, top, right, bottom] = bounds(mark).map((value) => value * scale);
      context.beginPath();
      context.ellipse((left + right) / 2, (top + bottom) / 2, (right - left) / 2, (bottom - top) / 2, 0, 0, 2 * Math.PI);
      context.stroke();
    } else if (mark.kind === "arrow") {
      const [tail, tip] = [at(mark.points[0]), at(mark.points[mark.points.length - 1])];
      context.beginPath();
      context.moveTo(tail[0], tail[1]);
      context.lineTo(tip[0], tip[1]);
      context.stroke();
      const [one, two] = arrowHead(tail, tip, width * 4);
      context.beginPath();
      context.moveTo(tip[0], tip[1]);
      context.lineTo(one[0], one[1]);
      context.lineTo(two[0], two[1]);
      context.closePath();
      context.fill();
    } else if (mark.kind === "text") {
      drawNote(context, mark, scale, imageWidth, imageHeight);
    } else if (mark.kind === "highlight") {
      const [left, top, right, bottom] = bounds(mark).map((value) => value * scale);
      context.globalAlpha = 0.3;
      context.fillRect(left, top, right - left, bottom - top);
      context.globalAlpha = 1;
    } else if (mark.kind === "strike") {
      const [from, to] = [at(mark.points[0]), at(mark.points[mark.points.length - 1])];
      context.beginPath();
      context.moveTo(from[0], from[1]);
      context.lineTo(to[0], to[1]);
      context.stroke();
    } else if (mark.kind === "insert") {
      const [x, y] = at(mark.points[0]);
      const half = Math.max(7, imageWidth / 90) * scale;
      context.beginPath();
      context.moveTo(x - half, y + half * 1.4);
      context.lineTo(x, y);
      context.lineTo(x + half, y + half * 1.4);
      context.stroke();
      drawNote(context, mark, scale, imageWidth, imageHeight);
    }
    drawBadge(context, mark, scale, imageWidth);
    context.restore();
  }

  /** A mark's number in a filled circle of its color. */
  function drawBadge(context, mark, scale, imageWidth) {
    const radius = Math.max(10, imageWidth / 90) * scale;
    const [x, y] = badgeAt(mark).map((value) => value * scale);
    context.beginPath();
    context.arc(x, y, radius, 0, 2 * Math.PI);
    context.fillStyle = mark.color;
    context.fill();
    context.lineWidth = Math.max(1.5, radius / 6);
    context.strokeStyle = "#ffffff";
    context.stroke();
    context.fillStyle = "#ffffff";
    context.font = `700 ${radius * 1.15}px sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(String(mark.n), x, y + radius * 0.05);
  }

  const api = {
    PALETTE, TOOLS, WORDED, Marks, bounds, tooSmall, arrowHead, badgeAt, strokeWidth, draw, drawBadge,
    wrap, noteLook, noteLayout, hitNote, measurer,
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ClankMarks = api;
})(this);
