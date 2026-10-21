# 0018. Policy rules combine by "deny wins": deny over ask, ask over allow, and no rule means deny

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
Whether something may happen is decided from layers of rules (design 0002 §2.6): Clank's safety floor, the
workspace's bounds and its own rules, the mode, and the grants the user gave. Different components and the user write
them, in different files. OpenCode's own permissions use "the last matching rule wins".

## Decision
Any *deny* wins. Otherwise any *ask* wins, unless a grant covers it. Otherwise the answer is *allow* if some layer
allows; if no layer has a rule, the answer is *deny*. A deny is a ceiling: no answer to a question and no grant passes
it, and the user allows what a rule denies only by changing that rule.

## Alternatives considered
- **The last matching rule wins.** The outcome depends on the order in which files are read, and a looser rule read
  later can undo a stricter one: a grant could undo plan mode.
- **The first matching rule wins.** The same problem the other way round, and hard to follow across several files.
- **Allow when no rule applies.** A forgotten rule would open access.

## Consequences
- Switching to a stricter mode always restricts, whatever was granted before.
- A new permission is denied everywhere until some layer allows it.
- Every policy decision names the rule that decided it, and the file and line where that rule is written.
- Where an agent program has permission settings of its own, its adapter writes Clank's rules into them; the program's
  settings never change Clank's.
