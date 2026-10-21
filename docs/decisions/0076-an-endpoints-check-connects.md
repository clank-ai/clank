# 0076. An endpoint's check connects: on a tunnel of its own, for the moment, with Clank's own made-up requests only

- Status: Proposed
- Date: 2026-10-18
- Decided by: Claude, with [design 0015](../design/0015-endpoints.md) §11, from the research of 2026-10-18 and its
  review of 2026-10-19; the owner approves or changes it with the design

## Context

- Design 0001 §3.8 (approved): a check "takes seconds and starts nothing". For an engine, everything a check needs can
  be read without a launch: the program, its version, the flags it accepts, the model's file, the memory fit
  (`clank/components/runtime/launching.py:200-242`).
- For an endpoint, almost nothing can be learned without connecting: whether the login accepts the key, whether the
  server refuses a wrong key and takes the endpoint's, whether it lists the model and with which context, whether it
  accepts tool calls (vLLM refuses tools sent without a `tool_choice` unless it was started with
  `--enable-auto-tool-choice` and a `--tool-call-parser`, its tool-calling documentation), and which field it streams
  thinking in (decision 0074).
- Design 0001 §7.6 (approved): "The guide tests a key with a request of a few tokens and lists the endpoint's models."
- The main slot's port may be held by a running engine (`clank/components/runtime/kinds.py:97-108`).
- Design 0001 §3.8 (approved) also has a *test*: a trial that runs test suites against a candidate. A candidate that
  fits beside the live model, as an endpoint does, "runs alongside it". Trials and their suites come with M2, and a
  login or a key must be checked before an endpoint's first load.

## Decision

- An endpoint's check connects: `clank endpoint check`, `clank preset check` of an endpoint preset, and the console's
  `c` on it. It is an operation, since it can take up to a minute.
- It opens a tunnel of its own, on a free port of the loopback, never a slot's, and closes it when done; when a slot
  already runs that endpoint, it uses that slot's tunnel instead. When M2 builds trials, an endpoint's trial runs
  alongside the live model the same way, as design 0001 §3.8 says.
- It sends only Clank's own made-up requests: a wrong key, the list of models, a reply of a few tokens to a fixed
  prompt, and a call to a made-up tool with usage asked for. Never anything of a workspace's. Nothing on the server is
  started, stopped or changed.
- What starts nothing comes first (the `ssh` program and its version, `ssh -G` on the tunnel's file, whether the
  service's SSH agent is alive, whether the key is set), so a check that cannot connect still says what it could
  verify. Then the job, when the endpoint names one, through the login host (design 0015 §5).
- An endpoint set `insecure` is flagged by every check, whatever else passes (design 0015 §2).
- Each item passes, fails or is unknown, with why, as an engine's check does; the result is kept as an event and shown
  with the endpoint.
- `clank endpoint models` and `clank endpoint preset`, which need the server's list, connect the same way.

## Alternatives considered

- **A check that starts nothing** (the program, `ssh -G`, the agent, the key). It could not say what matters: whether
  the server answers, whether it holds the key, with which context, and whether it takes tool calls.
- **The tunnel on the slot's own port.** It would collide with an engine the slot runs.
- **Leaving it to a trial.** An endpoint's trial runs alongside the live model (design 0001 §3.8), so it would stop
  nothing; but trials come with M2, and a trial runs whole suites where a key or a login needs a few made-up requests,
  before the first load.

## Consequences

- A check takes from seconds to a minute, and logs in to the jump host and the login host once (twice when it
  confirms a job); it never runs on a schedule of its own.
- Its made-up requests are Clank's own, not a workspace's content, so `model.send` (decision 0075) does not apply to
  them.
- The setup guide (M10) runs the same check for its "On another computer" step.
