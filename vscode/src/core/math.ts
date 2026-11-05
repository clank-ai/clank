// Math in the model's text (design 0021 §4), set aside before Markdown reads it so its underscores stay math, then drawn
// by KaTeX in its place: `$$…$$` and `\[…\]` as display math, `$…$` and `\(…\)` inline. Never inside code: a fenced
// block (three backticks or tildes, or more; one left open runs to the end, as Markdown reads it) or an inline code span
// (of one backtick or more) is kept as it is, so a shell's `$HOME`, a template's `${a}` and a ```latex block keep their
// dollar signs. Inline `$…$` opens on a character that is not a space and closes after one, never before a digit, so
// "$5 and $10" stays two prices (as Pandoc reads it). Import-free: the board's page loads it as it is (board.html).

const FENCE = /^ {0,3}(`{3,}|~{3,})[^\n]*(?:\n[\s\S]*?(?:\n {0,3}\1[`~]*[ \t]*(?=\n|$)|(?![\s\S]))|(?![\s\S]))/gm;
const SPAN = /(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n)[\s\S])*?[^`]\1(?!`)/g; // never across a blank line
const MATH = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$(?=\S)([^$\n]*?\S)\$(?!\d)|\\\(([\s\S]+?)\\\)/g;

export interface Split {
  text: string;
  math: Array<{ text: string; display: boolean }>;
}

/** Where the text's code is, fenced blocks first and then inline spans outside them: each [start, end). */
function codeRanges(text: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  for (const found of text.matchAll(FENCE)) ranges.push([found.index, found.index + found[0].length]);
  const inside = (at: number): boolean => ranges.some(([start, end]) => at >= start && at < end);
  const spans: Array<[number, number]> = [];
  for (const found of text.matchAll(SPAN)) {
    if (!inside(found.index)) spans.push([found.index, found.index + found[0].length]);
  }
  return [...ranges, ...spans].sort((a, b) => a[0] - b[0]);
}

/** A text with its math set aside (`@@MATHn@@` in its place), for Markdown to read; then each piece is drawn by KaTeX. */
export function splitMath(text: string): Split {
  const math: Split["math"] = [];
  const outside = (piece: string): string =>
    piece.replace(MATH, (_whole, display?: string, bracket?: string, inline?: string, paren?: string) => {
      math.push({ text: display ?? bracket ?? inline ?? paren ?? "", display: display !== undefined || bracket !== undefined });
      return `@@MATH${math.length - 1}@@`;
    });
  let kept = "";
  let from = 0;
  for (const [start, end] of codeRanges(text)) {
    if (start < from) continue;
    kept += outside(text.slice(from, start)) + text.slice(start, end);
    from = end;
  }
  return { text: kept + outside(text.slice(from)), math };
}
