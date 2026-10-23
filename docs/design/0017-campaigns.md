# Design 0017: campaigns, flows that do research

Roadmap part 11 (flows), extending [design 0013](0013-flows.md). Started 2026-10-23 at the owner's request, after the
first four long runs of a flow on an open problem. Every section is proposed; nothing here is built. It turns the
redesign the owner saw as an interactive diagram ("The Campaign Flow") into sections to approve one at a time, each
saying what it does, what motivated it, what the literature says, and what was rejected.

## Goal

The owner (2026-10-23): "context is king, so really giving these local models that perfectly relevant context is a
hugely important task here, and if we are clever enough we can give the LLM the proper toolset required to actually get
some real frontier-level work done", and "anything that is sufficiently difficult should be offloaded into these
flows", with "very, very good choices that are motivated from the work that already exists in the literature". The
literature used is only work released from 1 August 2026 on, as the owner asked; the survey behind it is
[docs/research/research-flows.md](../research/research-flows.md).

A campaign is a flow that does research: one question, pursued over as many runs as it takes, with a fixed way to
score progress, a portfolio of approaches, a search that improves its own method, a memory that outlives every session,
and a result that leaves only after it is verified. Its benchmark is the long runs' open problem, a public challenge on
stabilizer ranks: a verifier any result must pass, cells whose bounds are known, cells recently improved, and open ones.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the long runs showed | Proposed 2026-10-23 |
| 2 | Five principles from the literature | Proposed 2026-10-23 |
| 3 | The campaign | Proposed 2026-10-23 |
| 4 | The ruler and the gain floor | Proposed 2026-10-23 |
| 5 | The survey | Proposed 2026-10-23 |
| 6 | The portfolio of approaches | Proposed 2026-10-23 |
| 7 | The evolve box | Proposed 2026-10-23 |
| 8 | Jobs, side work and the corpus (built) | Built under design 0013 §17; restated here |
| 9 | Campaign memory | Proposed 2026-10-23 |
| 10 | Context packs and the event log | Proposed 2026-10-23 |
| 11 | The stop audit | Proposed 2026-10-23 |
| 12 | The verification ladder | Proposed 2026-10-23 |
| 13 | Running unattended | Proposed 2026-10-23 |
| 14 | The benchmark, and tuning the flow and the model | Proposed 2026-10-23 |
| 15 | The owner's choices | Proposed 2026-10-23: six questions for the owner; 2 and 3 answered the same day |
| 16 | Build order | Proposed 2026-10-23 |
| 17 | What this design does not cover | Proposed 2026-10-23 |
| 18 | The second model, chosen by measurement | Proposed 2026-10-23, at the owner's answer to §15 question 2 |
| 19 | Publishing: the blog on the website | Proposed 2026-10-23, at the owner's answer to §15 question 3 |

## 1. What the long runs showed

*Proposed 2026-10-23.*

Four runs of one flow (plan, check the plan, a pilot that recovers a known result, search, verify, join, final review)
on the local model, a 27B model on one 16 GB GPU, with the orchestrator steering (design 0013 §16):

- **The model plans and judges soundly.** It picked cells the attempt log had not tried, checked the board's files,
  caught its own arithmetic slip through the VERIFY (an exponent misstated in a fallback), caught two wrong counts in a
  search's report, and said plainly when a result would only match a published exponent.
- **The search is the limit, not the flow.** Seven cells came back null. In each, warm and cold starts of the
  challenge's annealer stopped at the same residual floors (for one cell, every one of 74 runs at 0.1042), far from the
  1e-9 a solution needs; the closest any cell came was 0.0111. More seeds of the same search found the same floors.
- **Waiting cost most of the time,** until jobs (§8): a search box's model sat in blocking calls for about nine tenths
  of its time.
- **Knowledge carried only by accident:** the third run read the second's null result because it was in the folder.
  With side work, the fourth run's plan picked its next cell from a side note; carrying it deliberately is §3 and §9.
- **Unattended gaps** (§13): a box asked the absent user a question (malformed: "Placeholder", no options) and waited;
  stopping a box left its processes running; the flow's accept command passed only on a new bound, so every honest null
  read as a failure the orchestrator had to take; a long recording was killed for want of memory.

## 2. Five principles from the literature

*Proposed 2026-10-23.* Each section below applies one or more.

1. **The score is computed outside the model.** Reward hacking is common when the agent controls the result and its
   evidence: 30.5% of open-ended research-pipeline tasks across 17 models, and an LLM panel reviewing code and reported
   scores missed 6.5% of confirmed hacks; the authors call for "metrics kept outside the agent's control" and
   independent recomputation (*Reward Hacking Challenges Oversight of Autonomous Research Agents*, arXiv:2609.28614,
   abstract). Only one of nine closed-loop research systems checked results against an external oracle
   (arXiv:2608.05179).
2. **Never steer by the model's own report of progress.** Agents' progress reports are reliable at some stages and not
   others, so "agent frameworks should not control task flow on the strength of the model's state reports alone"
   (arXiv:2609.08589, abstract); uncertainty mid-trajectory predicts failure poorly (no signal above AUROC 0.60 at half
   way), while confidence at the end separates outcomes well (0.85), so decisions belong at step ends
   (arXiv:2608.29685, abstract; EMNLP 2026).
3. **A simple loop first; machinery only when measured.** A seed solver, a scoreboard, a history of ideas, an
   independent verifier, keep or drop, and plateau detection broke 10 circle-packing records for $27.72
   (arXiv:2609.05093); single runs and single budgets mislead, and the best split between seeds and iterations
   depends on the task (*Evolution or Illusion?*, arXiv:2609.19799).
4. **One writer of memory, proposals audited.** Removing the single memory writer cut recall from 57.8 to 44.7, and
   removing the auditor that treats "end" as a proposal cut it to 52.1, on gpt-oss-20b and Qwen3.5-27B (Harness-Search,
   arXiv:2610.05382).
5. **Context is an environment, not a transcript.** An append-only log with outputs kept outside the prompt and
   landmarks pointing back reached 86.7% on LOCA_256K on Qwen3.8 (Scroll, arXiv:2608.21690); compaction loses the exact
   wording rules need, so episodes are summarized and rules never (arXiv:2608.22752).

## 3. The campaign

*Proposed 2026-10-23.*

A campaign is a flow with a question, a ruler (§4) and a record that carries from run to run: its memory (§9), its
corpus (§8), its best verified score, and its approaches with their state (§6). A run ends at its final review or its
budget; the next run starts from the record, never from nothing. A verified result (§12) closes the campaign, or
becomes the reference the next campaign starts from.

- **Kept** in Clank's state beside the flow's runs (`campaign.json`), Clank its only writer (principle 4), and shown in
  the Flow view as each run's best score and trajectory.
- **Made** as a flow is today, built with the model (design 0013 §15), with two more things fixed with the owner: the
  ruler and the budget per run.
- **Motivated by** the third run's accidental learning (§1) and Épi's campaigns over sessions, 120 record results with
  each verified result the next campaign's reference (arXiv:2610.24944).
- **Rejected**: one long run per question (a run does not survive a restart, a model change or a night without a
  carried record); each run starting fresh (runs repeat dead ends).
- **Done when** a second run skips the first run's dead ends without being told.

## 4. The ruler and the gain floor

*Proposed 2026-10-23.*

Before any search, the campaign fixes what "better" means: a command that scores a candidate (the verifier, run by
Clank), the number it prints, which direction is better, and the gain floor, the smallest change that counts as
progress (a 1% relative drop in residual to start). The model never states a score; Clank runs the ruler on what the
model produced and keeps the result (principle 1). The ruler and its files are read-only to every box: a box that
changes them fails, as a box that leaves its deliverable untouched does today.

- **Kept**: each evaluation's score, its candidate, its cost, and the run's best and trajectory, in the event log
  (§10).
- **Motivated by** the second and third runs judging progress in words, residuals read out of logs; Épi's fixed ruler
  and gain floor; principle 1.
- **Rejected**: the model reporting its own score (it would grade itself); a ruler per box (runs stop being
  comparable).
- **Done when** the Flow view shows each run's best score and trajectory from Clank's files alone.

## 5. The survey

*Proposed 2026-10-23.*

The first box of a run maps the ground before planning: what is open, what was tried at what cost (from the attempt
log and the campaign's memory), what the corpus says, and where the gaps look smallest. It writes `MAP.md` and states
its interpretation of the brief in one paragraph, which the plan and the verification ladder check against (§12, rung
4). A Plan-mode box, 30 minutes and 150,000 tokens.

- **Motivated by** the plan doing this inside its own time in every run; *Beyond Final Scores*: research agents act
  "more like engineering optimizers than fully autonomous researchers", and reused experience can mislead
  (arXiv:2608.13417, abstract), so the map says what was tried and how it ended.
- **Rejected**: a literature search whose claims are not checked: a claim from a source is confirmed in it or marked
  unconfirmed.
- **Done when** the map lists every open target with its attempts and cost from the log.

## 6. The portfolio of approaches

*Proposed 2026-10-23.*

The plan names two to four genuinely different approaches, each with its target, method, first cheap test (under 20
minutes) and the result that would make it worth continuing. Each is a recoverable state: its branch in the folder's
git, its files, its handover note and its best score. The orchestrator picks which approach runs next and may return to
one set aside; an approach is set aside when the ruler shows no gain over the floor at three checkpoints in a row.

- **Motivated by** runs two to four putting everything on one method (the annealer at short schedules); ScienceFlow's
  recoverable executable states, re-anchored at each transition, 70.22% any-medal on MLE-bench in 24 hours
  (arXiv:2608.14354, abstract); Épi's branch per approach, each abandoned one kept with its reason. Principle 2: an
  approach is set aside by the ruler's numbers, not by the model saying it is stuck.
- **Rejected**: all approaches at once (one GPU, one model: they take turns, jobs share the CPU); a tournament of plans
  judged by the model (the ruler judges them by what they score).
- **Done when** a run moves to a second approach when the first stalls, and back again.

## 7. The evolve box

*Proposed 2026-10-23.*

A new type of box that improves a search program rather than running one. It starts from a seed solver (for the
benchmark, the challenge's own annealer). Each iteration the model reads the scoreboard and the history of ideas tried,
proposes one change to the program (a move set, a schedule, a symmetry, a different method), and Clank runs the
candidate as a job and scores it with the ruler; an improvement is kept, a failure dropped with its reason written to
the history. When the best score stops moving (no gain over the floor in five iterations), the box ends and says so;
the orchestrator may then send it one conjecture of a different kind, chosen from the survey and the corpus, before
the approach is set aside.

- **Limits**: 15 to 40 iterations per approach, then a checkpoint; each candidate a job at most 16 threads with a cap
  of its own; the candidate cannot edit the ruler (§4).
- **Motivated by** §1: the floors were the method's, so the leverage is in changing the method. The circle-packing loop
  (principle 3). *The Little Scientist* (arXiv:2608.16951, abstract): a scientist agent with structured diagnostics,
  and a "Kuhn agent" that injects "a paradigm-shifting conjecture" when it plateaus, produced a leading protein-fitness
  method and a motif-discovery algorithm beating the default (AUROC 0.842 against 0.803) on one machine without GPUs.
  Station's supervisor and meta reflection "encourage persistent exploration even when intermediate metrics are
  lacking" (arXiv:2610.08927, abstract).
- **Rejected**: a full evolutionary framework from the start (islands, diversity archives): unmeasured machinery, added
  only when the benchmark shows a gain (principle 3); the model writing decompositions directly (its leverage is the
  program, not the space).
- **Done when** it recovers known bounds faster than the plain annealer at equal CPU hours, over several seeds.

## 8. Jobs, side work and the corpus (built)

*Built under [design 0013 §17](0013-flows.md) (decision 0132); restated here because the rest builds on it.*

A box starts any command expected to run more than two minutes as a job with `flow_job` and waits with its clock
stopped; while a job runs, a checkpoint of the orchestrator decides `wait`, `side` (one to three side tasks, each
writing one note into `corpus/`) or `change`; Clank keeps the corpus's index and hands it to every box and checkpoint.

**Measured in the fourth run:** five jobs; the box waited 26 minutes on one with its clock stopped; the orchestrator
chose `wait` for short jobs and `side` for a 35-minute one; a side task wrote a 12 KB note shortlisting three fallback
cells, and when the search came back null the next plan picked the note's first choice. The jobs' and side tasks' own
time is not yet counted against a machine cap (§13).

## 9. Campaign memory

*Proposed 2026-10-23.*

A record that outlives every session, of three kinds: **facts** (verified properties of the problem and the
environment), **attempts** (what ran, its settings, cost and score) and **dead ends** (an approach abandoned, with its
evidence). Entries are tagged by target, method and file. Clank writes every entry, from structured fields the boxes
and checkpoints give (an attempt from the ruler's record; a dead end from a set-aside decision; a fact from a box's
handoff field `facts`), at the end of each box, never from a model editing the memory freely (principle 4). When a box
uses an entry it marks it confirmed or contradicted; contradicted entries leave later packs.

- **Motivated by** each run's pilot rediscovering the same workaround; Épi's lessons and dead ends, retrieved and never
  replayed; REALM: updating a memory each time it is used (arXiv:2609.16053); LycheeMemory V2: consolidating at
  segment boundaries rather than every turn cut construction tokens by 86.0% on LoCoMo without costing accuracy
  (arXiv:2608.12990, abstract), here a box's end.
- **Rejected**: the whole history in context (attention to old material fades, principle 5); an embedding model at
  first (tags cost no GPU memory; retrieval by meaning is added if the benchmark shows tags miss).
- **Done when** settings that failed are not repeated on the benchmark.

## 10. Context packs and the event log

*Proposed 2026-10-23.*

Each box's first message is assembled, not accumulated: instructions, the ruler, the brief, the flow's map, the memory
entries sharing the box's tags (and the five newest), the corpus index, the handover notes, then the task. Stable parts
come first, so the engine's prompt cache stays warm across boxes. Everything a run produced is kept whole in an
append-only event log; a box sees landmarks (what a piece is, its size, where) and fetches any piece back with a new
tool, `flow_recall`. Rules, the ruler and decisions are never summarized; only episodes are (principle 5).

- **Motivated by** Scroll and the compaction cliff (principle 5); the local engine reads nearly all of each prompt from
  its cache when the prefix is stable, which a reshuffled first message throws away.
- **Rejected**: a summary of the run in every box (it changes the prefix and loses wording).
- **Done when** `clank flow prepare` shows each pack's parts and sizes, and a run keeps a high share of each prompt
  read from cache.

## 11. The stop audit

*Proposed 2026-10-23.*

Neither a box saying it is done nor the orchestrator stopping a run is final: an auditor, a fresh session handed the
brief, the ruler's numbers, the memory's attempts and the budget left, never the proposer's reasoning, accepts or names
the gap, which becomes the next box's note. It runs at step ends, where the evidence is (principle 2).

- **Motivated by** the second run stopping with most of its budget left on one plateau and a claimed "genuine barrier"
  nothing checked; Harness-Search's auditor (principle 4); *Last Step Matters* (principle 2).
- **Rejected**: a fixed rule such as stopping after N failures (it cannot tell a dead approach from a short one).
- **Limits**: 10 minutes, 30,000 tokens.
- **Done when** no run with budget left stops on one null without an audited reason.

## 12. The verification ladder

*Proposed 2026-10-23.*

A result leaves the campaign only by climbing five rungs, cheapest first; nothing is called new before the last:

1. **The ruler**, by machine: the score passes the solved threshold.
2. **Exact checks**: an exact refit and the challenge's verifiers exit 0, run by Clank (§4).
3. **A blind reviewer**: a VERIFY in a fresh session that never sees the box's reasoning, checking the result and its
   provenance; Clank also plants checks the result must fail when wrong (a known bound, a vacuous claim).
4. **The interpretation check**: what the box says it solved, against the survey's interpretation of the brief (§5).
5. **The novelty check**: the live board, open proposals and the literature, each citation confirmed in its source.
   A verified result is committed to a local branch at once; making it public stays the owner's.

- **Motivated by** principle 1 (independent recomputation; with detailed feedback, evasion reached 40.5% of model-task
  pairs against 20.3% with a plain rejection, though the authors note the comparison does not isolate the explanation,
  so a refusal here says what failed, not how the check works); the
  verification-gap survey (about 38% of systems report any novelty check, arXiv:2608.05179); the pilot already
  climbing rungs 1 and 2 on known results.
- **Rejected**: the orchestrator's own reading as a rung (it judges; it does not verify).
- **Done when** a planted vacuous result and a planted known result are both caught.

## 13. Running unattended

*Proposed 2026-10-23.* What the fourth run showed a flow running alone needs:

- **A box's question goes to the orchestrator** while it steers, as a question checkpoint does, with the box's session
  waiting for the answer; malformed questions (no options, placeholder text) are refused back to the box at once.
  Off, it goes to the owner as today (§15, question 5).
- **A null is an outcome, not a failure.** An accept command may exit 2 for "ran correctly, found nothing", recorded as
  a null with its evidence and passed to memory as an attempt (§9), so the orchestrator stops having to take a
  failure.
- **A stopped box's processes end.** Processes a box started that outlive its try are ended with it, as a job's are
  (§15, question 6).
- **A machine cap**: the flow's jobs and side tasks run under a memory and CPU limit set per workspace, so the
  owner's machine stays responsive and nothing is killed for want of memory (§15, question 4).

## 14. The benchmark, and tuning the flow and the model

*Proposed 2026-10-23.*

The flow is tuned the way the evolve box tunes a search: every change to a prompt, a setting or a box is scored on a
fixed suite, over several seeds, with cells held out. **Tier A**: recover known bounds; **tier B**: cells whose best
bound fell recently; **tier C**: open cells; some A and B cells never used for tuning. Each report gives the
seeds-by-iterations frontier and process measures beside scores: model idle time, dead ends repeated, time per box,
share of prompt read from cache. `clank bench` runs it unattended and writes the comparison.

What is measured on it, each adopted only on a held-out win over several seeds:

- **Prompts and instructions per box**, tuned on this model's own runs: correcting a weaker open model's own failing
  turns helped where copying a stronger model's trajectories hurt it on every task, by 4 to 30 points
  (arXiv:2609.09134); harnesses evolved for one family transferred to others (StarHarness, arXiv:2608.24804); harness
  optimization is measurable but depends on the optimizer, and native harnesses were not reliably better
  (HarnessOpt-Bench, arXiv:2608.06301, abstract). For small models the large gains came from optimizing harness and
  weights together, and in mathematics harness search helped only after a weight update (WHALE, Qwen3.5-2B and 4B,
  arXiv:2609.00196, abstract), so prompt tuning alone is expected to give modest gains.
- **The model's settings**: the speculative draft length, thinking on or off per box type, and sampling per role;
  community figures (95 to 101 tokens a second for this model on a 16 GB card with a draft length of 2 and thinking
  off) are measured here before they decide anything. The second model is chosen by its own protocol (§18).

- **Rejected**: tuning on open cells (it chases noise in the cells that matter); adopting any figure unmeasured.
- **Done when** `clank bench` writes the comparison table overnight, unattended.

## 15. The owner's choices

*Proposed 2026-10-23; questions 2 and 3 answered by the owner the same day.* Questions whose answers change what is
built; Claude's recommendation first.

1. **The benchmark before the evolve box?** Recommended: yes, so the evolve box is measured from its first version.
2. **A second, faster model for side tasks and the auditor?** *Answered:* "I am open to using a second, faster model for
   the side tasks, but we should really carefully curate this second model and make sure that we are finding one that
   is both extremely fast as well as extremely useful for the task we will give it." How it is chosen: §18.
3. **The benchmark's results public?** *Answered:* "Yes, I am fine with benchmark results made public, let's include
   this as a bit of a personal blog portion on the clank-ai website. I want us to be as public as possible with the way
   that we are configuring things, especially with the way that we have frankensteined together the kvmem setup with
   the swift 1.5 qwen3.8-27b model." What is published, and how: §19. Results on open cells are published once
   verified (§12), as any result.
4. **A machine cap** for flows: the share of memory and CPU threads jobs and side tasks may use? Recommended: 75% of
   memory and all threads but two, changeable per workspace.
5. **A box's questions while the orchestrator steers**: to the orchestrator, or still to the owner? Recommended: to the
   orchestrator, with a word to the owner when it answers.
6. **Ending a stopped box's leftover processes** automatically? Recommended: yes, listed in the box's events.

## 16. Build order

*Proposed 2026-10-23.* Each step a plan with tests first, as every milestone (design 0001 §8.6):

1. The benchmark (§14), tier A first, and the ruler (§4): everything after is measured on them.
2. Running unattended (§13) and campaign memory (§9).
3. The evolve box (§7), measured against the plain annealer.
4. The stop audit (§11) and the verification ladder (§12).
5. The survey and the portfolio (§5, §6), context packs and the event log (§10), the campaign record (§3).

The second model's trial (§18) runs on the benchmark once step 1 is built; the blog (§19) starts with the setup's
post, which needs nothing new, and gains the benchmark's results as they come.

## 17. What this design does not cover

*Proposed 2026-10-23.*

Training or fine-tuning the model's weights (WHALE suggests it matters for small models; it is a separate design and
needs more GPU than this machine has); several GPUs or machines running a campaign at once; cloud models as searchers
(a campaign may name one as any flow may, under design 0016's rules); making a verified result public (always the
owner's act).

## 18. The second model, chosen by measurement

*Proposed 2026-10-23, at the owner's answer to §15 question 2.*

A second model runs side tasks (§8), and may run the stop audit (§11), only if it is measured, on this machine, to be
both much faster at that work and as useful as the main model. Where it runs matters as much as which model it is:

- **This machine**: the main model fills the GPU (15.3 of 16 GB in use while it runs); the CPU has 16 cores and 32
  threads with 64 GB of DDR5-4800; and side tasks run exactly while a job is using up to 16 of those threads.
- **On the CPU, beside the main model.** Mixture-of-experts models with about 3B active parameters decode at usable
  speed on this CPU: gpt-oss-20b, measured on the same processor model with llama.cpp's CPU backend, generated 27
  tokens a second but read a prompt at about 145 tokens a second
  ([OpenBenchmarking, 2025](https://openbenchmarking.org/result/2509087-NE-9950X3DLL86)). An agent's session sends
  15,000 to 30,000 tokens of prompt, so each turn would wait minutes for its prompt, and the job would lose cores to it.
- **On the GPU, in turns with the main model.** While a box waits on its job, the main model is idle: Clank could switch
  the main slot to a faster model for the side tasks and back before the box resumes. The cost is two switches per job
  and the main model's prompt cache, which the box's resumed session then reads again.
- **Beside a smaller main context.** A preset of the main model with less context frees GPU memory for a small second
  model at once; the cost is the main model's context.
- **The main model itself, faster.** The baseline every candidate must beat: the same model with thinking off and its
  speculative draft tuned, which needs no second model and no switch.

**Usefulness is measured on side tasks with checks**, drawn from the long runs: shortlist next targets from the attempt
log and the board (each claim checked against the files); write a script a later box needs (run against a test the
benchmark keeps); examine a job's partial output (its figures checked against the log); summarize a paper's method
(each citation found in its source). Each candidate's notes are scored by those checks and compared blind with the
main model's notes on the same tasks; malformed tool calls are counted, since a side task is an agent session.

**Speed is measured end to end** on the same tasks: time from a side task's start to its note, including prompt
reading and any switch of the main slot, while a benchmark job runs, and the job's own slowdown.

**Adopted** only when, over several seeds of the side-task suite, a candidate (in one placement) is no worse than the
main model on the checks, finishes the suite in at most half its time, and slows the job by at most 10%; otherwise the
main model keeps the side tasks. The comparison, every candidate's numbers and the reasons for the choice go on the
blog (§19).

**Candidates to start**, each released before the trial and chosen for few active parameters and native tool calling:
gpt-oss-20b (about 3.6B active; its 4-bit file fits the GPU alone), the Qwen3.6-35B-A3B mixture of experts (3B
active), a Gemma 4 mixture of experts with about 4B active, and Qwen3-Coder-30B-A3B for script writing; the list is
read again when the trial starts, for anything newer.

- **Rejected**: choosing by public leaderboards (they score other tasks, on other hardware); a second model on the CPU
  without measuring prompt reading (the figure that decides an agent's speed there).

## 19. Publishing: the blog on the website

*Proposed 2026-10-23, at the owner's answer to §15 question 3.*

The website gains a blog, written for the owner and in their voice, which says openly how Clank is configured on their
machine and what it measured: as public as possible about the configuration, including the parts that were pieced
together.

- **The setup's post first**: the main model as it runs (Swift 1.5, Qwen3.8-27B retrained, in its IQ3_S file with the
  MTP head, on KVMem with 262K of context and system memory), why each piece was chosen and what was tried and dropped,
  the exact files with their checksums and the engine's flags, the measured speeds, and what broke along the way (a
  graphics driver that crashed the engine, the decode speed that halved). It builds on
  [docs/models/frontier-262k.md](../models/frontier-262k.md), which already holds most of it.
- **Benchmark posts**: each run of the benchmark (§14) with its table, its seeds and its process measures, and each
  change adopted or rejected with its numbers; the second model's trial (§18) in full.
- **Campaign posts**: what a campaign tried and why it ended, nulls included; a verified result only once it has
  climbed the ladder (§12) and the owner has made it public.
- **Never published**: anything that identifies the machine or the owner beyond what they choose (user names, paths,
  host names, GPU identifiers, keys), and the owner's research outside the benchmark.
- **How**: Claude drafts each post from Clank's own files (the benchmark's tables, the run records, the measurement
  pages), the owner reads and edits it, and only the owner's approval publishes it on the site.

## Sources

All released from 1 August 2026 on; "abstract" marks those read only through their abstract.

- arXiv:2608.05179, *Autonomous Research Agents: A Survey of AI Scientists and the Verification Gap*.
- arXiv:2608.06301, *HarnessOpt-Bench: Evaluating LLMs at Harness Optimization* (abstract).
- arXiv:2608.12990, *LycheeMemory V2: Efficient Long-Term Memory for LLM Agents via Semantic Segment-Level
  Consolidation* (abstract).
- arXiv:2608.13417, *Beyond Final Scores* (abstract).
- arXiv:2608.14354, ScienceFlow (abstract).
- arXiv:2608.16951, *The Little Scientist: LLM Agent-Driven Discovery via the Scientific Method* (abstract).
- arXiv:2608.21690, Scroll, *Context as an Environment*.
- arXiv:2608.22752, the compaction cliff.
- arXiv:2608.24804, StarHarness.
- arXiv:2608.29685, *Last Step Matters: Early Uncertainty Cannot Predict Failure in Long-Horizon Agents* (abstract).
- arXiv:2609.00196, *WHALE: A Simple Recipe for Joint Harness-Weight Optimization* (abstract).
- arXiv:2609.05093, circle-packing records with a simple loop.
- arXiv:2609.08589, *The Unreliable Progress Bar* (abstract).
- arXiv:2609.09134, co-evolving harnesses and models.
- arXiv:2609.16053, REALM, retrieval-driven memory reconsolidation.
- arXiv:2609.19799, *Evolution or Illusion?*.
- arXiv:2609.28614, *Reward Hacking Challenges Oversight of Autonomous Research Agents* (abstract).
- arXiv:2610.05382, Harness-Search.
- arXiv:2610.08927, *Can AI Agents Make Open-Ended Scientific Discovery? Evidence from Station* (abstract).
- arXiv:2610.24944, Épi.

## Decisions to record

Numbered when approved: a campaign and its record (§3); the ruler run by Clank and read-only to boxes (§4); the evolve
box (§7); Clank the sole writer of campaign memory (§9); the stop audit (§11); the verification ladder (§12); a null as
an outcome (§13); the benchmark as the measure of every change to a flow or a setting (§14).

## Revision log

- **2026-10-23**: the owner answered §15's questions 2 (a second model, carefully chosen) and 3 (results public, on a
  blog on the website, as public as possible about the configuration); §18 and §19 added, §14 and §16 changed to
  point to them.
