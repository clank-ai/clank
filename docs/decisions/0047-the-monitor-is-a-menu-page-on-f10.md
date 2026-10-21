# 0047. The Monitor is a page of the console's menu on F10, with three views: Flow, Session and Context

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §2's two Choices as recommended

## Context
The owner (2026-10-18) asked for "a new section of the menu for Clank where we can explicitly monitor EVERYTHING the
local model is doing, similarly to the way that we have the prototype's monitor working, but this time it needs to be
entirely inside the CLI on a new tab on the left", a place "to help guide the model as well as just monitor the
model", and one "easy for me to navigate". The owner liked board A the most, and called board D's guiding "VERY MUCH
what I have been having in mind". [Design 0012](../design/0012-the-monitor.md) §2 lays out the page. F11 is Windows
Terminal's full screen, and the name "Monitor" already belongs to the machine column in the code.

## Decision
- The page is **Monitor**, on **F10**, listed after F9 (the menu sorts its F-keys as strings today; that is fixed).
  F12 takes its place if F10 does not reach the console. The machine column's code is renamed `MachineColumn`
  ([design 0011](../design/0011-the-consoles-look.md)'s R2), and keeps F5.
- Three views, in a row of tabs: **Flow** ([design 0013](../design/0013-flows.md)), **Session** (board A) and
  **Context** (board C). F10 again, on the Monitor, moves to the next view; Enter on the Context window panel opens
  the Context view, and Enter on a box of the Flow view opens its session; Esc goes back. The page opens on the view
  last shown.
- The Session view is board A with board D's **Watch for** and **Guide** as two small panels under Now; an action
  that cannot run is grayed there, with its reason.
- The machine column is hidden on the page by default (F5 shows it): in a terminal 160 columns wide, the page has
  about 88 columns beside it and about 128 without it.
- The page belongs to the agents component. It takes over the live watching and guiding planned for the menu's
  **Agents** page (M5); **Sessions** (M3) stays the list of each slot's conversations, and Enter on one opens it here.

## Alternatives considered
- **A monitor apart from the console**, like the prototype's: the owner asked for this one inside the console.
- **F11**: Windows Terminal takes it for full screen.
- **The capitals `S`, `C` and `F` for the views**: new letters, which could clash with a panel's letter or a Guide key.
- **Watch for and the Guide as keys only**, as board A draws them (a note line at the page's foot, marks only in the
  flow): an action that cannot run would not show its reason on screen, which the transparency rule asks for.
- **Board B as a view of its own**: the flow already lists the steps; board B's right half became a step's details.

## Consequences
- Whether F10 reaches the console in Windows Terminal is measured before step 1.
- Beside "Monitor" the menu shows ● while the followed session works, and the count of marks not yet seen; the header
  gets a pill for the session's phase.
- The page is on screen while the model writes: it redraws at most four times a second, only what changed, and nothing
  while idle, and the model must decode at 95% or more of its speed with the page on screen, measured before steps 2
  to 6 are built (§2's pass mark, with its fallbacks).
