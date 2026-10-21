# 0082. A Watch for mark told to the phone is listed with what waits, and an action that cannot run tells the phone instead

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-19
- Decided by: Claude, without the owner ([plan s18](../plans/s18-monitor-watch-for.md)'s calls 6 and 7, building
  design 0012's step 8); it makes [0053](0053-watch-for-rules-run-in-the-service.md)'s "tell the phone" and its
  actions exact

## Context
Decision 0053 lets each Watch for rule mark, pause the session, tell the phone, or tell the model and go on
([design 0012](../design/0012-the-monitor.md) §8). Two things it leaves open matter when the rules are built:

- **How the phone is told.** The phone page already lists what waits: OpenCode's permissions and questions, and Clank's
  own questions (`kernel.questions`), which the console's Questions page and VS Code show too ([design
  0005](../design/0005-the-phone.md) §6). Push alerts do not exist yet ([decision 0012](0012-the-phone-page-and-push.md)).
- **What a rule does when its action cannot run.** The note to the model is design 0012's step 9 and the pause its
  step 11; neither is built with step 8. Later, a note may be refused (the bridge cannot reach the session, its
  container stopped). The default rule after a loop guard stop tells the model, so that a run left alone goes on; if
  the note cannot go, the run sits idle.

## Decision
- **A mark told to the phone is listed, not asked.** The phone's overview lists the marks told to it and not seen yet
  (`marks`), and the page draws each with what waits: its rule, its session, why, and what its rule could not do and
  why. "Seen" takes it off (`POST /api/marks/seen`), recorded as the device's; a mark seen anywhere else (the console's
  Enter on Watch for, `POST /agents/marks/seen`) leaves the list too. A mark of an ask the page already shows in
  OpenCode's own box (a permission, a question) is not listed again, and one whose ask no longer waits (answered) leaves
  the list: the phone lists each ask once. Push alerts carry it once they exist.
- **An action that cannot run tells the phone instead.** When the note or the pause is not built yet, or is refused,
  the mark records that action as not done with the reason ("telling the model comes with the Guide's note (design
  0012 §11 step 9)", the bridge's own words), and the phone is told, "instead of" that action. A note that could not
  go does not count toward the rule's notes in a row.

## Alternatives considered
- **A Clank question for each mark told to the phone.** Questions already reach the phone, the console and VS Code,
  and survive a restart. But a mark waits for no answer, and a question needs at least two options and an answer from
  someone; the Questions page and VS Code would each have shown it again as something to decide.
- **An action that cannot run does nothing more.** The mark alone shows on the Monitor, which no one may be watching:
  a run stopped by the loop guard would sit idle, and the owner, not watching, would not know.
- **Send the note now through the bridge's `prompt`.** Step 4 built it, with the session's agent and model. Design 0012
  says the note comes with step 9 (the Guide's note, with what it is about and its states), and that the loop guard's
  stop leading to an idle session is still to measure before step 8; sending notes before both would build step 9
  twice.

## Consequences
- With step 8 alone, the default rule after a loop guard stop tells the phone, saying the note waits for step 9; step 9
  gives `Marks.acting` its `note`, step 11 its `pause`, and nothing else changes.
- The marks are kept in memory, as the flows are ([decision 0049](0049-a-sessions-flow-is-built-in-the-service.md)):
  after a restart they are made again from the flows, those on steps and on the owner's notes from before Clank
  watched (every step finished by then, and the notes those steps decided) kept as seen and doing nothing more, so a
  mark the phone was told and not seen leaves its list.
