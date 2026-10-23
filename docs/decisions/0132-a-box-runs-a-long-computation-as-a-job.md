# 0132. A box runs a long computation as a job; while it runs, the orchestrator has the model

- Status: Accepted (the owner's two choices of 2026-10-23: the box asks for a job; the orchestrator decides what is done
  while it runs)
- Date: 2026-10-23
- Decided by: the owner (the two choices), Claude (the rest)

## Context
- In the second long run the search box ran its campaign as blocking `bash` calls of about five minutes each; the
  local model, the machine's only one, wrote nothing for nine tenths of the box's time.
- The owner: while a computation runs the model should work on something else, or the box end its turn and the
  orchestrator have the model, to review the run, branch the flow, or set side research going that builds up a corpus
  of knowledge for what the run will need later.

## Decision
- **A job** (design 0013 §17): a box starts a long computation with `flow_job`; Clank runs it detached in the
  container, its files in `.clank/jobs/` in the folder; the box's turn ends and its try waits, its clock stopped; when
  the job ends, the same session is told how it ended and goes on. A box has one job at a time; a job is limited by
  its `minutes`, at most its box's.
- **While it runs**, with the orchestrator on, a checkpoint (kind `job`) decides: `wait`, `side` (up to three side
  tasks, each a session that writes one note into the corpus), or `change` (the boxes ahead, a diverging path among
  them). Side work is bounded per task and per run.
- **The corpus**: `corpus/` in the folder, its index `CORPUS.md` kept by Clank, handed to every box and checkpoint.

## Alternatives considered
- **Clank detaching any call that runs long** (the owner's other option): no OpenCode interface stops a call and lets
  the session go on; the box asking is explicit and visible.
- **Always side research** or **only a review** (the owner's other options): the orchestrator, which knows the run,
  decides, within limits.
- **A second model, or two requests at once**: the machine's one model serves one request well; side work uses the
  time the model would sit idle.

## Consequences
- Long computations no longer hold the model; a box's try may span hours of job time, its own limit counting its
  model's work only.
- Side tasks and the resumed box take the model in turn when both work; the main line comes first (no side task starts
  after its job ended).
