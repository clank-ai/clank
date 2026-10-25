// Design 0018 §7.2 and §7.3: the files the agent opened (the event `agents.shown`) are read from the event with their
// folder and why, and opened only by a window on that folder (Windows' folders compared without case, either slash, a
// trailing slash or not); the paths the agent prints as the container sees them (`/workspace/...`) are found in a line
// of its terminal, each with where it starts and its length, a line or column number after it and the punctuation that
// ends a sentence left out. Design 0020 §9: the PDF of a LaTeX change waiting for review (`agents.latex_diff`) opens
// the same way, beside the change's diff.

import assert from "node:assert/strict";
import { test } from "node:test";

import { containerLinks, markedUp, sameFolder, shown } from "../src/core/show";

test("an agents.shown event gives its workspace, folder, files and why; any other gives nothing", () => {
  const data = {
    id: 51,
    type: "agents.shown",
    summary: "the agent opened plots/residual.png in paper's VS Code window",
    subject: { kind: "workspace", id: "paper" },
    data: { workspace: "paper", folder: "C:\\Research\\paper", files: ["plots/residual.png"], why: "asked for" },
  };
  assert.deepEqual(shown({ name: "agents.shown", id: 51, data }), {
    workspace: "paper",
    folder: "C:\\Research\\paper",
    files: ["plots/residual.png"],
    why: "asked for",
  });
  assert.equal(shown({ name: "agents.annotated", id: 52, data }), undefined);
  assert.equal(shown({ name: "agents.shown", id: 53, data: { data: { folder: "x" } } }), undefined, "no files");
});

test("a LaTeX change's PDF is opened as a file the agent showed, its why saying what it is", () => {
  const data = {
    id: 61,
    type: "agents.latex_diff",
    data: {
      workspace: "paper",
      folder: "C:/Research/paper",
      change: "per_1",
      file: "main.tex",
      pdf: ".clank/latex/per_1/diff.pdf",
      marked: true,
    },
  };
  assert.deepEqual(markedUp({ name: "agents.latex_diff", id: 61, data }), {
    workspace: "paper",
    folder: "C:/Research/paper",
    files: [".clank/latex/per_1/diff.pdf"],
    why: "the change to main.tex, marked (red: removed, blue: added)",
  });
  const fresh = { ...data, data: { ...data.data, marked: false, pdf: ".clank/latex/per_1/note.pdf", file: "note.tex" } };
  assert.equal(markedUp({ name: "agents.latex_diff", id: 62, data: fresh })?.why, "note.tex, as built");
  assert.equal(markedUp({ name: "agents.shown", id: 63, data }), undefined);
});

test("a window opens them only when it is on that folder", () => {
  assert.ok(sameFolder("c:\\research\\paper", "C:\\Research\\paper\\", true));
  assert.ok(sameFolder("C:/Research/paper", "C:\\Research\\paper", true));
  assert.ok(!sameFolder("C:\\Research\\paper2", "C:\\Research\\paper", true));
  assert.ok(!sameFolder("/srv/research/Paper", "/srv/research/paper", false), "elsewhere, case counts");
  assert.ok(sameFolder("/srv/research/paper/", "/srv/research/paper", false));
});

test("container paths in a line of the agent's terminal are links to the folder's files", () => {
  const line = "Saved /workspace/plots/residual.png and `/workspace/notes.md`, see /workspace/src/fit.py:42.";
  assert.deepEqual(containerLinks(line), [
    { start: 6, length: 29, relative: "plots/residual.png" },
    { start: 41, length: 19, relative: "notes.md" },
    { start: 67, length: 21, relative: "src/fit.py" },
  ]);
  assert.deepEqual(containerLinks("cd /workspace && ls /workspace/"), [], "the folder itself is no file");
  assert.deepEqual(containerLinks("(/workspace/a b.txt)"), [{ start: 1, length: 12, relative: "a" }]);
  assert.deepEqual(containerLinks("/workspace/../etc/passwd"), [], "nothing outside the folder");
});
