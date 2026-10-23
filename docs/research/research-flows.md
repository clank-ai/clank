# Research flows: what makes a local model do frontier work

A survey made on 2026-10-23, after the first three long runs of a flow on an open problem (a public challenge on
stabilizer ranks, Clank's benchmark from now on), at the owner's request: "context is king, so really giving these local
models that perfectly relevant context is a hugely important task here, and if we are clever enough we can give the LLM
the proper toolset required to actually get some real frontier-level work done", the model itself tuned "from the
individual parameters like the temperature all the way to things like the best possible prompts", for 16 GB cards and
the RTX 5080. Only work released from 1 August 2026 on is used, as the owner asked. It follows
[orchestration.md](orchestration.md), which shaped the orchestrator.

## What the three runs showed

- The local model planned, judged and reported soundly: it picked cells the run log had not tried, checked its claims
  against the board's files, and said plainly when a result would not beat a published exponent. Its orchestrator, on
  the same model, decided every checkpoint by tool, with evidence.
- What failed was the search: the challenge's annealer at 20,000 iterations, about five minutes a seed, plateaued at
  the same residual from warm and cold starts (0.294 on one cell, 0.2549 on another, 0.2807 and 0.2905 on a third),
  where a solution needs 1e-9. The open cells survived the challenge's own automated loop with the same tool.
- The model sat idle for about nine tenths of the search box's time, its tool call blocking (design 0013 §17 answers
  that).
- A failure ended the second run where the flow had no other way to go; given `back`, the third run's orchestrator sent
  the work to the plan with what was learned, and the plan chose another orbit.

## What the field found (August to October 2026)

- **A simple loop breaks records.** A September paper ([arXiv:2609.05093](https://arxiv.org/abs/2609.05093)) broke 10
  Packomania circle-packing records, accepted by Packomania, for $27.72 in 15 iterations: a seed solver, a scoreboard,
  a history of ideas, an independent verifier, improvements kept and failures dropped, adaptive plateau detection.
- **Measure search over seeds and budgets.** *Evolution or Illusion?* ([arXiv:2609.19799](https://arxiv.org/abs/2609.19799))
  found single-seed, single-budget comparisons mislead: the best split between width (seeds) and depth (iterations)
  depends on strategy, task and budget, and rankings shift with them.
- **Persistent research agents keep memory outside the context.** Épi ([arXiv:2610.24944](https://arxiv.org/html/2610.24944v1)),
  120 record results: lessons with evidence and dead ends with reasons, retrieved not replayed; a handover note at each
  session's end; a branch per approach; long experiments as jobs; a fixed ruler with a gain floor; an independent
  reviewer of claims of progress; campaigns over sessions.
- **Recoverable states and compute by progress.** ScienceFlow ([arXiv:2608.14354](https://arxiv.org/abs/2608.14354)):
  segments kept as recoverable executable states, re-anchoring on a live or archived one at each transition, an
  evidence-aware controller giving compute to jobs by budget and validated progress (70.22% any-medal on MLE-bench in
  24 hours).
- **Propose, commit, audit.** Harness-Search ([arXiv:2610.05382](https://arxiv.org/html/2610.05382)), on gpt-oss-20b and
  Qwen3.5-27B: one memory writer (removing it cut recall from 57.8 to 44.7), an auditor that treats "end" as a proposal
  (removing it cut recall to 52.1).
- **Context as an environment.** Scroll ([arXiv:2608.21690](https://arxiv.org/abs/2608.21690)), on Qwen3.8: an
  append-only event log, outputs kept outside the prompt, landmarks pointing back; 86.7% on LOCA_256K, 37.4 points above
  the best published long-horizon agent. The compaction cliff ([arXiv:2608.22752](https://arxiv.org/html/2608.22752v1)):
  rules lose their exact wording in compaction; summarize episodes, never rules. REALM
  ([arXiv:2609.16053](https://arxiv.org/abs/2609.16053)): memories updated each time they are used.
- **Harnesses for weaker open models.** Co-evolving harnesses and models ([arXiv:2609.09134](https://arxiv.org/abs/2609.09134)):
  training a weaker open model on a stronger one's full trajectories hurt it on all seven tasks (-4 to -30 points);
  correcting only its own failing turns worked. StarHarness ([arXiv:2608.24804](https://arxiv.org/pdf/2608.24804)):
  evolved harnesses transferred across GPT and Qwen families.
- **What research agents are now.** Beyond Final Scores ([arXiv:2608.13417](https://arxiv.org/abs/2608.13417)): agents
  behave "more like engineering optimizers than fully autonomous researchers", rarely novel; process metrics matter;
  reused experience can mislead. The verification gap ([arXiv:2608.05179](https://arxiv.org/pdf/2608.05179)): one of
  nine closed-loop systems checked results against an external oracle; about 38% reported any novelty check.
- **The model on a 5080.** Qwen3.8-27B was released on 14 August 2026; its GGUF carries an MTP head. Community runs on
  a 16 GB RTX 5080 reached 95-101 tokens a second with `--spec-type draft-mtp --spec-draft-n-max 2` and thinking off
  ([qwen38-mtp](https://github.com/sudoingX/qwen38-mtp), [5080-llm-configs](https://github.com/BFinn/5080-llm-configs));
  this machine's preset decodes about 63-67 with thinking on. q4_0 KV buys room for context, not speed.
- No stabilizer-rank result from this window turned up, and none of this work applies model-guided search to
  stabilizer rank.

## What Clank takes

The redesign is [design 0017](../design/0017-campaigns.md), proposed; it was first drawn as an interactive diagram (the
owner's artifact "The Campaign Flow"); its stages, each with what
it does, why, what motivated it and what was rejected: the campaign; the brief and ruler with a gain floor; a survey;
a portfolio of two to four approaches kept as recoverable states; the evolve box, starting as the record-breaking loop;
jobs (design 0013 §17, approved); the orchestrator's job checkpoint, side tasks and re-anchoring; the corpus; campaign
memory kept by Clank alone with confirmation on use; context packs over an event log; stopping as a proposal an
auditor accepts; a five-rung verification ladder; integration into memory; and the benchmark (tiers of known, recently
moved and open cells, several seeds, held-out cells) on which every setting of the flow and the model is measured.

Several papers were read through their abstracts only; community and blog figures are to be measured here before they
decide anything.
