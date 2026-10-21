# 0064. The model changes a flow only by proposals, accepted by the owner or by auto-accept within a cap

- Status: Accepted (the owner approved design 0013 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0013](../design/0013-flows.md) ("Approve all three"); where accepted boxes
  go, and what a DECOMPOSE run again does, are Claude's calls in its §9

## Context
The owner: "the model will have the ability to access this flowchart and create new items if it needs to (especially
when a plan is then being broken up into individual actionable chunks)." Yet the owner steers the flow, and a rule is
enforced where it can be stopped ([decision 0020](0020-enforce-where-it-can-be-stopped.md)), as the agent's writes to
Notion are staged for the owner ([decision 0039](0039-notion-through-the-service-changes-reviewed.md)).
[Design 0013 §9](../design/0013-flows.md#9-the-model-proposes-boxes) says how the model adds boxes.

## Decision
- Clank's MCP server, `clank` (design 0005 §3), gains `flow_read`, `flow_propose_box`, `flow_submit` and
  `flow_verdict`, answered by the service through the gateway's `/flows/` routes. Only proposals: the gateway refuses
  anything else under `/flows/` (403), the service refuses an acceptance that comes from the agent, and the flow's
  file is out of the container's reach ([0066](0066-a-flow-is-a-settings-file-in-clanks-home.md)).
- Any box may propose, DECOMPOSE above all. Each proposal is checked when staged and refused with its reason: the type
  and the preset exist, `after` names a box of the flow, the deliverable lies in the folder and is no file agents load
  as settings or instructions, the prompt is not empty, and the flow still keeps its rules
  ([0057](0057-a-flow-is-a-chain-of-boxes.md)).
- Proposals gather in a batch in the run's folder and wait: the owner accepts, edits then accepts, or rejects each, or
  accepts all. Auto-accept, a flow setting off by default, lets those that pass the checks join at once, marked as
  accepted by the setting, up to a cap per run (10); beyond it they wait.
- Accepted boxes join the flow's file, written by the service (an edit the owner makes on the version it replaced is
  refused, with both versions shown), each marked with the run and the box that proposed it; the batch keeps the
  history of what was proposed and decided.
- A DECOMPOSE run again proposes anew: its new proposals replace its tasks that have not started; those that ran stay,
  marked stale when their inputs changed, for the owner to keep or remove.
- The planner's rules (design 0009 §3) gain these tools, which write nothing in the folder.

## Alternatives considered
- **Boxes the model adds join at once.** The owner would not decide what the flow runs; auto-accept does so only when
  the owner turns it on, after the checks, marked, and within a cap.
- **Accepted boxes kept in the run only.** The owner asked that the model create new items in the flowchart; in the
  file, the next run starts from them.
- **A DECOMPOSE run again replacing every task it added.** Tasks that already ran would leave the flow without the
  owner deciding.
- **The planner without these tools.** PLAN, VERIFY, DECOMPOSE and INTEGRATE could not all run in Plan mode.

## Consequences
- The gateway forwards a few more routes that are not the model's, and the sandbox image's MCP server grows four tools.
- A proposal goes to the box running in its workspace (the MCP server knows no session; one box runs at a time,
  [0061](0061-the-runner-is-an-operation-per-box-in-the-service.md)), or, with none running, to the flow it names.
