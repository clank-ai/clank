# 0097. A flow is built by talking it through: the model drafts it in a planning session, Clank checks it and writes the flow's file

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: Claude, building the owner's request ([design 0013 §15](../design/0013-flows.md#15-a-flow-built-with-the-model),
  [plan s32](../plans/s32-flows-a-flow-built-with-the-model.md)): "for starting the flow I need the ability to use the
  LLM to build the flow at the beginning, and then I want to let the flow go from there", and their first answer:
  "describe it by talking it through: `n` in the Flow view, or `clank flow new [name]`, opens a planning session ...
  The model reads the folder, asks the owner questions, then writes the brief and the flow. Clank checks the flow and
  shows it on F10."

## Context
A flow is a settings file in Clank's home, out of every sandbox's reach, so the rule that the model only proposes is
enforced where it can be stopped (decisions 0020, 0064, 0066). Until now the model could only propose boxes into a
running flow (`flow_propose_box`); a whole flow was written by the owner, by hand or from Clank's template. Building a
flow by talking it through needs a way for the model to hand Clank a whole flow, for Clank to say what is wrong with it
so the model can fix it, and a place for the conversation. The container's MCP server knows its workspace and not its
session (design 0010 §7), so a tool call cannot be tied to one session.

## Decision
- **A planning**, opened by `n` (or `N`) in the Flow view or `clank flow new [NAME]`, is a record of the service
  (`state/flows/<workspace>/<name>/building.json`, its first message beside it): one open per workspace, a newer one
  setting the older aside. Its name is the one given, else `flow`, `flow-2`, ...; an existing flow's is refused.
- **The planning session** is a fresh OpenCode session sent to the planner (Plan mode) with a first message from
  `clank/components/flows/prompts/build.md`, filled in by Clank, which overrides the Planner's own instructions
  (`planner.md`: a plan file with a `kind: plan` header, `/implement`) wherever they differ; a second agent for it
  would join OpenCode's Tab order (revised before shipping, at the review, 2026-10-20): what a flow is, the box types and their rules, the
  file's fields, the presets of the main slot with their windows, the owner's three answers, Clank's template (its
  plan's gate taken out) as the example, the template's model by default, and how to talk it through: read the
  folder, ask a few questions at a time, write `BRIEF.md` with the owner, then `flow_draft` and fix what Clank says.
- **`flow_draft(flow)`**, a tool of Clank's MCP server, sends the whole draft. The gateway forwards `POST /flows/draft`
  as the client `agent`, its exact allowlist gaining that route alone; the service gives it to the planning open in the
  workspace the server names, as a verdict goes to the VERIFY at work there, and refuses it with none open, or once
  the flow it builds has run.
- **Checked, then answered.** A draft is checked as a saved flow (§3's rules, presets, workspace) and against a built
  flow's own rules (decision 0098). Problems are refused (409), each named with its field; the check's warnings
  (decision 0087) come with them, or with the flow written.
- **Clank writes the file**, `config/flows/<workspace>/<name>.json`: the draft's title, defaults, boxes and lines, with
  Clank's settings over the draft's (the workspace, auto-accept on, no wait after any box, `next_flow` ask, the
  template's model when none is named, and `built`: the session, when, the brief). A later draft replaces it until the
  flow first runs. `flows.built` records each; the owner is told as decision 0098 says.

## Alternatives considered
- **The model writes the flow file itself**, in the folder (design 0013 §11's option (a)): refused when §11 was decided;
  the agent's commands can write any file of the folder unasked, so the check would come after the fact.
- **A box proposing the boxes one by one** (`flow_propose_box` into an empty flow): a flow is a chain with rules that
  hold only whole (a VERIFY's two lines, a fan's join), so single boxes would fail the rules until the last; and
  proposals wait for a run, which a flow being built has not.
- **The planning tied to its session** rather than its workspace: the MCP server cannot tell sessions apart (design
  0010 §7); one planning per workspace gives the same guarantee for the case that happens, a second planning setting
  the first aside, said.
- **Clank turning the conversation into a flow itself** (a second model call after the session): the owner asked that
  the model write the flow, and fixing a draft against Clank's own words keeps the model in the loop that knows the
  folder.

## Consequences
The model never writes a flow's file; it drafts, and Clank decides what is written. The sandbox image changes (the MCP
server's new tool, the bridge's planner start: decision 0099), so a workspace's container is made again from it once
stopped. A draft from a box's model while a planning is open in its workspace would be taken as the planning's: boxes
are not told of `flow_draft`, and the owner looks before running (decision 0098). A planning does not survive a
restart of the service while its session is being started; `n` starts another. A planning is refused in a
workspace whose container runs an older sandbox image, naming the fix (stop the workspace and open it again).
