# Plan s46: jobs for the agent

Builds [design 0021](../design/0021-all-llm-work-in-clank.md) §6, approved by the owner on 2026-10-25: the agent the
owner talks to starts a long computation (a simulation, a build, a sweep) as a job and goes on, instead of holding its
session on a shell command that OpenCode stops after at most 10 minutes. Flows' jobs (plan s43) are the same jobs. Each
task starts with a failing test; each ends with a commit pushed to `main`.

## Tasks

- [x] 1. **The job runner in the workspaces** (§6): the container part of flows' jobs (`START`, `END`, `ALIVE`, `start`,
  `end`, `alive`, `read_state`, `tail`, `written`, `span`) moves to `clank/components/workspaces/jobs.py`, given to
  other components through `workspaces/service.py`; `flows/jobs.py` keeps what is a flow's (its folder, what a box is
  told). Every job runs at the lowest CPU priority (`nice -n 19`), so the model keeps its speed. Tests: flows' job
  tests unchanged; the start's command line.
- [ ] 2. **The agent's jobs in the service** (`agents/jobs.py`): start (a number, its folder
  `.clank/jobs/agent/<n>/`, its title, command, minutes and the session that started it in `job.json` beside the
  runner's files), list, one (state, time, the log's last lines, the files written) and stop; a watcher ends a job past
  its minutes and, when one ends, records `agents.job_ended` and tells the session that started it in a message (how
  it ended, its log's end, the files it wrote). Routes: `POST /agents/jobs`, `GET /agents/jobs?workspace=`,
  `GET /agents/jobs/{workspace}/{n}`, `POST /agents/jobs/{workspace}/{n}/stop`; the gateway forwards the agent's.
- [ ] 3. **The agent's tools**: `run_job(command, title, minutes)`, `job_status(job)` and `job_stop(job)` in Clank's MCP
  server; the instructions (`jobs.md`): a command expected to run more than two minutes is a job.
- [ ] 4. **Seeing jobs**: `clank jobs` (each workspace's, or one's), a notification in VS Code when one ends (Open its
  log), and the readout's line of running jobs.
- [ ] 5. **The model keeps its speed**: writing speed measured with a CPU-heavy job running at normal and at the lowest
  priority (`bench/speedtest.py`), and the result recorded in design 0021 §6.

## Progress

Written 2026-10-25.
