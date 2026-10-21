# 0053. "Watch for" rules run in the service over each session's flow, each doing what the owner sets

- Status: Accepted (the owner approved design 0012 on 2026-10-18); made exact by
  [0082](0082-a-watch-for-action-that-cannot-run-tells-the-phone.md) (an action that cannot run tells the phone
  instead) and [0083](0083-notes-in-a-row-count-again-after-a-clean-step.md) (what "in a row" counts)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §8's Choice as recommended

## Context
The owner wants the Monitor to be "a place for me to help guide the model as well as just monitor the model"
([design 0012](../design/0012-the-monitor.md) §8). Some states call for the owner, or for an answer, when no one is
watching: an approval waiting, the same call made again and again, failures in a row, a limit near. The loop guard
stops an answer that repeats itself and leaves the rest to the Monitor ([decision
0040](0040-the-gateway-stops-an-answer-that-repeats-itself.md)): "Telling the model what happened and going on by
itself is the Monitor's to decide (a rule the owner sets), not the guard's."

## Decision
- Each rule is a **pure function over a session's flow**, run in the service whenever the flow changes, so rules act
  while no console is open.
- Each **mark** shows on its node in the flow, in the Watch for panel and beside "Monitor" in the menu; `?` on it says
  what it rests on.
- What each rule does is the owner's to set, in a readable settings file, `config/monitor.json` (a settings kind with
  its schema): **mark** it; **pause** the session; **tell the phone** (the phone page lists it, and push alerts carry
  it once they exist, [decision 0012](0012-the-phone-page-and-push.md)); or **tell the model and go on**, a note in
  the rule's words.
- **Telling the model is capped**: at most twice in a row for the same rule in a session; after that, the rule marks,
  pauses and tells the phone.
- The rules and their defaults are those of §8's table. After a loop guard stop, the default is to tell the model and
  go on ("Clank's loop guard stopped your last answer because it repeated itself, and that answer is not in your
  context. Go on from where you were, without writing it the same way again."), the cap and the note's cost shown in
  the mark.

## Alternatives considered
- **After a loop guard stop, mark and tell the phone**, the session waiting for the owner: a run left alone would stop
  at its first loop.
- **Rules run in the console**: they would act only while a console is open.
- **The loop guard telling the model itself**: decision 0040 left that to a rule the owner sets.

## Consequences
- The rules are built in step 8; telling the model needs the note (step 9), and pausing needs the hold (step 11).
- A rule's facts come from OpenCode, the gateway or the flow, so some rules wait for steps 2 to 5.
- A Guide action a rule takes (a pause, a note) leaves an `agents.acted` event saying a rule did it.
