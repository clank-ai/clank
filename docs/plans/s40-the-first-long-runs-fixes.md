# Plan s40: the first long run's fixes, and the orchestrator's word for the owner

[Design 0013](../design/0013-flows.md) §5 and §16, decisions
[0127](../decisions/0127-the-orchestrator-tells-the-owner-at-once.md) and
[0128](../decisions/0128-a-runner-looks-at-a-session-itself.md). From the first long unattended run (2026-10-22),
stopped by the owner, and the owner's request that followed: the orchestrator on the local model,
"after each completed step just to make sure things are on track and to get my attention if there is anything that I
need to be aware of out of nowhere."

**Goal:** a run whose boxes end when their sessions end, an orchestrator that can give its decision and reach the
owner, and Claude conducting the next long run, fixing what it finds.

## What the first run showed

- The PLAN ended after 25 minutes with its plan and handoff note written; the runner waited for its limit of 30 and
  failed it. The orchestrator's checkpoint ended after 91 seconds; the runner waited for its 20. Their sessions
  counted 0 tokens: the runner heard nothing of them (OpenCode's stream silent after its instance ended).
- The checkpoint, on the local model, decided well (take the plan as it is, with a note for the check) but wrote its
  decision as text: `flow_decide` was not among the Plan mode's tools (Clank's list for the planner lacked it).
- After the run asked a question, it did not look again whether the orchestrator should decide it until something
  else woke the runner.

## Tasks

- [x] 1. The watch opens a server's stream again after `server.instance.disposed` (the fake OpenCode's `dispose` as
  OpenCode 1.19's, measured), when it does not say it is connected (one opened as OpenCode starts never does: found in
  the second run), and after two minutes of silence. Test: `tests/components/agents/test_monitor_watch.py`.
- [x] 2. The runner reads a box's and a checkpoint's session status itself every minute (`LOOK`). Test:
  `tests/components/flows/test_runner_controls.py` (a box that ended unheard), the fake bridge's `finish_unheard`.
- [x] 3. The planner gets `flow_decide` (`CLANK_FLOW_TOOLS`). Test: `tests/components/agents/test_agent_servers.py`.
- [x] 4. A checkpoint that ends without deciding is reminded once in its session; still none, the question is the
  owner's. Tests: `tests/components/flows/test_orchestrator.py`.
- [x] 5. After asking a question the runner looks again at once (the orchestrator may decide it). Test: the same file
  (a run paused and resumed before its gate).
- [x] 6. Its word for the owner (`tell_user`, a question of high urgency the run does not wait for: Seen, Pause, Stop),
  `pause` after a box, `leave` at a question, the role `watch`; the instructions check the run is on track. Tests: the
  same file.
- [x] 7. The way in: `flow_decide`'s `tell_user`, the routes' `role`, `clank flow orchestrator --role`, the panel's
  role, model and last word, `O` cycling steer, watch, off. Tests: `tests/cli/test_flow_commands.py`,
  `tests/console/test_orchestrator_panel.py`.
- [x] 9. From the second run: at a failed box's question the orchestrator may send the work `back` (with `back_to` and
  a note), the question withdrawn; its instructions on stopping with budget left, on claims, and on good news; a box's
  first message names its deliverables already in the folder. Tests: `tests/components/flows/test_orchestrator.py`,
  `tests/components/flows/test_first_message.py`.
- [ ] 8. The next long run, conducted by Claude: the workspace's image built again (the bridge and Clank's MCP server
  are in it), the service restarted, the run started with the orchestrator steering, watched and fixed as it goes.
