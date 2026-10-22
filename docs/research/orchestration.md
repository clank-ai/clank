# Orchestration: what others built, and what Clank takes from it

Notes from a survey made on 2026-10-22, before Clank's orchestrator was designed (design 0013 §16): how systems that
let models work for hours on their own steer that work, what Clank takes from each now, and what is kept here for
later design choices. A claim marked *(secondary)* was read in a summary of the source, not in the source itself.

## The systems

### Magentic-One (Microsoft): an orchestrator with two ledgers

[arXiv:2411.04468](https://arxiv.org/abs/2411.04468); the pattern as
[Microsoft Agent Framework's magentic orchestration](https://startdebugging.net/2026/10/what-is-magentic-orchestration-in-microsoft-agent-framework/)
and [agentpatterns.ai](https://agentpatterns.ai/patterns/multi-agent/magentic-orchestration/) describe it *(secondary)*.

- A **task ledger** (the facts given, the facts to look up, educated guesses, and the plan) and a **progress ledger**,
  answered at every round as five fields: is the request satisfied, are we looping, is progress being made, who acts
  next, and what they are told.
- A **stall counter** rises when no progress is made or the team loops, and falls otherwise; past a limit, the
  orchestrator rewrites its facts and plan and starts the team again (a *reset*).
- In Microsoft's framework the limits on rounds and resets default to unlimited, and must be set.

**Clank takes now:** the ledger as a file the orchestrator reads at every checkpoint; the five questions as the
fields of its decision; the stall counter and the new plan past its limit; limits that are always set.

### Anthropic's multi-agent research system: delegation and effort

[How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system);
[ByteByteGo's summary](https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent) *(secondary)*.

- A lead agent plans and hands tasks to subagents that work in parallel; a subagent given a vague task duplicates
  work or leaves gaps, so each is given an objective, an output format, its tools and its boundaries.
- Agents judge effort badly: the lead's prompt carries **effort-scaling rules** (how much work a kind of question is
  worth).
- Many agents cost far more tokens than one (about fifteen times a chat, by one summary) and suit broad work better
  than tightly coupled work such as code.

**Clank takes now:** a box the orchestrator adds or rewrites keeps a box's full contract (its prompt, what it sees,
what it writes, what accepts it); the orchestrator's prompt carries effort rules tied to the budget left.

### Anthropic's harnesses for long-running agents: state outside the model

[Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents);
[a summary of its patterns](https://jiangren.com.au/en/learn/ai-engineer/long-running-agent-harness) *(secondary)*.

- A first session sets the work up; every later session reads a **progress file written for the next agent** (what
  is done, what is next, what blocks) and the history, checks that things still work, does one piece, and records it.
- The list of requirements is locked: a session may only mark an item passing or failing.
- Compaction is no substitute for durable state, testable definitions of done, and checkpoints one can return to.

**Clank takes now:** every checkpoint is a fresh session that reads the ledger (Clank's boxes already work this way,
with their handoff notes); the brief's "done means" lines are the locked list: the orchestrator may never change
`BRIEF.md`, only report each line met or not.

### AlphaEvolve (DeepMind), OpenEvolve and FunSearch: the evaluator decides

[OpenEvolve, an open implementation of AlphaEvolve](https://huggingface.co/blog/codelion/openevolve);
[AlphaEvolve explained](https://composio.dev/blog/alphaevolve-evolutionary-agent-from-deepmind) *(secondary)*;
[FunSearch in LLM4AD](https://llm4ad-doc.readthedocs.io/en/latest/method/funsearch.html).

- A model proposes changes to a program, an **automatic evaluator** scores each, and a **program database** keeps the
  best and the most varied (MAP-Elites, islands that evolve apart and are reseeded from the best); the best are put
  back in the next prompts.
- An **evaluation cascade**: cheap tests first, so weak candidates are dropped before the costly ones.
- FunSearch's results were constructions in combinatorics (cap sets, bin packing): the kind of object a stabilizer
  decomposition is.

**Clank takes now:** a machine check outranks every model's opinion: the orchestrator weighs a box's accept command
(the verifier, a test) above a VERIFY's verdict and above its own reading.
**Kept for later:** a *search* box: a program evolved against an evaluator, with a database of candidates and their
scores, run by the flow for hours. It is the most promising shape for problems like the Stabilizer Rank Challenge.

### The AI Scientist v2 (Sakana AI): a tree of experiments, and its warnings

[Paper](https://arxiv.org/abs/2504.08066); [summary](https://huggingface.co/papers/2504.08066).

- An experiment manager steers a **best-first tree search** over experiment nodes, in stages, with no human template.
- Its fully autonomous papers were later found to contain hallucinated and overclaimed results, and its novelty was
  overestimated; the authors advise a sandbox for the code it runs.

**Clank takes now:** no claim of novelty is taken from a model: the orchestrator reports what the checks confirmed,
and the owner judges what is new.
**Kept for later:** a *tree of tries*: a box whose failed try branches into differing alternatives, the best kept,
instead of one line of retries.

### The Stabilizer Rank Challenge's own research loop

`stabrank/autoresearch/README.md` in the challenge's repository (Apache-2.0).

- Every run, successful or not, is one line in a log that is never edited; a result counts only once refit in exact
  arithmetic; a near miss is recorded, never submitted.
- Failures are classed (a miss, a near miss, a timeout, an out-of-memory kill, an infrastructure error) and **only
  infrastructure failures are retried**; a cap per job, so nothing is killed to meet a deadline.
- An operability line (hours covered, share of them with a job running, the longest gap) is the evidence that a loop
  ran unattended.

**Clank takes now:** the orchestrator is told each failed try's class and retries only what failed for a cause
outside the work; a run's log already keeps every try.
**Kept for later:** an operability summary per run (the share of the run's hours a box was working).

## Also kept for later

- **Parallel workers** for broad work (Anthropic): on one GPU the model serves one session at a time, so Clank runs
  boxes in turn; parallel tasks suit a machine with room for several sessions, or a cloud model.
- **A tournament of alternatives** (Google's AI co-scientist, from memory: hypotheses ranked in pairs by a model,
  Elo-style, the best evolved): for choosing between plans a PLAN box drafted.
