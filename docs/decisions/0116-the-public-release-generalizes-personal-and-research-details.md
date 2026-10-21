# 0116. The public release generalizes personal and research details in earlier records

- Status: Accepted; amends earlier records in place, the one exception to "never edited away"
- Date: 2026-10-21
- Decided by: the owner, preparing Clank's first public beta: the public repository must hold none of the owner's
  personal information, the details that are only worth fixing included

## Context
Clank was built in a private repository, its records written as the work went: decisions, designs, plans and
measurements quote the owner, name the owner's own projects and tools, and say when and where the work was done. The
public repository is a fresh one, exported as a single commit, so the records go out as they stand. Records are never
deleted or rewritten ([README.md](README.md)); a later decision supersedes an earlier one. That rule keeps the reasons
for every choice; it was never meant to publish a person's life with them.

## Decision
Before the export, the details below are generalized where they appear, in decisions, designs, plans, measurements,
boards, tests, shipped prompts and code. What each record decided, why, and what was measured stays as it was.

- **The owner's research**: their simulator, its tools, its tests and its repository, their studies, their research
  questions, the layout of their research databases, and their study repository. A made-up example takes their place
  (`myproject`, a small random-walk simulator; Papers and Concepts in Notion).
- **Affiliation**: an institution, its cluster, its network or its computers, and the owner's research group. "A
  remote server", "a cluster you have access to" and "another computer" take their place.
- **Personal life and schedule**: when the owner was away, asleep, in a meeting or busy, and the hours a run took
  place. The dates stay; the facts measured stay.
- **The owner's desk**: monitors and their refresh rates, games, a processor's integrated GPU. The hardware a
  measurement ran on (the RTX 5080 and its 16 GB) stays, since the presets are sized for it.
- **Private tools**: the earlier private prototype Clank began from is "the prototype" ([PROTOTYPE.md](../PROTOTYPE.md));
  its containers and the owner's other projects are neither named nor recognized by Clank's code.
- **Words sent to every user's model**: the shipped prompts speak of "the user", and quote no one.

The private repository keeps the full history, with every record as first written.

## Alternatives considered
- **Publish the history as it is.** It keeps every record untouched, but publishes the owner's research and life.
- **Leave the records out of the public repository.** It protects the owner, but a reader could no longer ask why:
  the records are how Clank explains itself (principle 3, radical transparency).
- **A superseding decision for each record touched.** It keeps the rule to the letter, but would add dozens of records
  that say nothing about Clank.

## Consequences
- A record in the public repository may differ from its first version in these details only; this decision says so.
- New records keep to the same rule from now on: nothing personal, no one's research, no private tools' names
  (AGENTS.md, "Nothing personal or secret in the repository").
