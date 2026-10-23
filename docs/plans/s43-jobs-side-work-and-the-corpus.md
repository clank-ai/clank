# Plan s43: jobs, side work and the corpus

[Design 0013](../design/0013-flows.md) §17, decision [0132](../decisions/0132-a-box-runs-a-long-computation-as-a-job.md).
Asked for by the owner on 2026-10-23, its two choices made the same night.

**Goal:** a long computation never holds the model: a box starts it as a job and waits; meanwhile the orchestrator
reviews the run and may set side tasks going, whose notes build the flow's corpus.

## Tasks

- [x] 1. Jobs in the container (`clank/components/flows/jobs.py`): start detached (`setsid`, `timeout`), its folder
  `.clank/jobs/<flow>/<run>/<box>-<n>/` (command, log, pid, exit), its state read as files, ended by Clank past its
  minutes or when the run stops. Tests: `tests/components/flows/test_jobs.py`, against the fake platform.
- [x] 2. The way in: `flow_job` in Clank's MCP server, `POST /flows/job` (the gateway's flows allowlist), the runner's
  `job` (only the box at work, one job at a time, at most its minutes). Tests: the forwarding test, `test_jobs.py`.
- [x] 3. The box waits on its job: its turn ended with a job running is not its end; its clock stopped; the job's end
  sent to the same session (exit code, time, log's tail, files written, side notes). Tests: `test_jobs.py`.
- [x] 4. The `job` checkpoint: `wait`, `side` (1-3 tasks), `change`, `tell_user`; side tasks run one after another
  while the job runs, each a session on the flow's server in Auto mode writing one note; limits per task and per run.
  Tests: `tests/components/flows/test_side_work.py`.
- [x] 5. The corpus: `corpus/CORPUS.md` kept by Clank; handed to every box's first message and every checkpoint.
  Tests: `test_first_message.py`, `test_side_work.py`.
- [ ] 6. The instructions: a box's (start any command expected to run more than two minutes as a job), the
  orchestrator's (what to do while a job runs). The view and the Flow view: the job on its box, in Selected, the Side
  work panel; Thinking follows the session at work. Tests: the console's.
- [ ] 7. A long run with jobs, conducted by Claude.
