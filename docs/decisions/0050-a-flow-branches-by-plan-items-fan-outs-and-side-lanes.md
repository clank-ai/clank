# 0050. A session's flow branches by plan items, fan-outs and side lanes, all on one graph

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §6.2's Choice as recommended; what a plan item
  is was Claude's call (2026-10-18), approved with the design

## Context
The owner asked that the flow "should be more of a branching out effect rather than just a linear chart"
([design 0012](../design/0012-the-monitor.md) §6.2-§6.4). A session offers several kinds of branch: the plan it
carries out, calls made at once, subagents, failures, undone steps, and OpenCode's fork (a new session with no link
back, sharing the same files). OpenCode's todo list arrives whole with each `todo.updated`, and its items have no ids.

## Decision
- A branch is one of three kinds, all on one graph:
  - **a plan item**: a numbered checklist step of the Clank plan the session carries out (`/implement`, design 0009
    §5.1), stable and ticked by the implementer; else an item of OpenCode's todo list, matched across revisions by its
    text, a guessed match marked; without either, the owner's messages and the runs of calls between them. A step
    joins the item that was in progress when it started;
  - **a fan-out**: calls made at once, which open from their step and join again at the next; a subagent, from the
    `task` call that started it to what it gave back;
  - **a side lane**: a dead end (a call in the error state, or a `bash` call whose exit status is not 0), which leaves
    the main line once the agent moves on and ends in ⊘; an undone step.
- **Other histories** (forks) wait for a branch of the files too, a git worktree for instance.
- As board A draws it: time runs down, and the branches open to the right, joined by box-drawing lines aligned in
  columns, drawn by a pure function, `render(view, width, cursor, folds)`.

## Alternatives considered
- **A linear chart**: the owner asked for branches.
- **Any one kind alone**: plan items alone would hide calls made at once and subagents; fan-outs or side lanes alone
  would hide the plan's shape.
- **Forks now**: a fork shares the same files, so it needs a branch of the files too, which does not exist yet.
- **The todo list ahead of a Clank plan**: its items have no ids and are matched by their text, at a guess; a plan's
  numbered steps are stable.
- **Textual's tree widget**: it gives an indented outline, not a fan-out.

## Consequences
- An inference (a dead end, a guessed match, a repeat) says in its details what it rests on.
- Room is tight: about 88 columns beside the machine column, about 128 without it; under about 70 the branches stack
  under their node. Snapshot tests pin the alignment, and the style file can name plain marks for a terminal that
  draws ●, ✓ or the box-drawing lines wide.
- The layout has not been tried in a terminal; step 6 prototypes it against the boards.
