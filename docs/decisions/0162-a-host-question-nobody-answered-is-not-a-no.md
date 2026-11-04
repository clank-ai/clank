# 0162. A host question nobody answered is not the owner's no

- Status: Accepted (the owner's report of 2026-10-29 and the audit of 2026-10-30); revises design 0024 §3
- Date: 2026-11-04

## Context

- When the agent reaches a host its workspace does not allow, the proxy holds the connection for 60 seconds while
  Clank asks the owner (design 0024 §3). Unanswered, the request was refused with the words of a refusal ("the owner
  was asked and did not allow it"), and the host was not asked for again for ten minutes.
- While OpenCode has the terminal, the console's question is not on screen: the owner's `git clone` and `pip install`
  waited a minute on a question nobody saw, then the agent said the owner had refused, and asking again was refused at
  once for ten minutes. Dev mode no longer asks (decision 0152); everywhere else this went on.

## Decision

- **A question that expired or was withdrawn is unanswered**, never a no: the service's decision says `unanswered`,
  no quiet period begins, and the next request for the host asks again.
- **The agent is told so**: the host is not allowed yet, the owner has not answered (they may not be watching Clank),
  so it asks the owner in its reply, and says how they allow it (in the console, VS Code or the phone, or `clank
  workspace allow` with `--host`). The proxy's log says `asked: unanswered`.
- **The owner's no keeps its quiet period**, as before, so a retrying program does not flood them.

## Alternatives considered

- **Hold the connection longer**: programs give up on a silent connection after a minute or two, and the agent's turn
  waits meanwhile.
- **Show the question in OpenCode's terminal**: the terminal is OpenCode's; the console beside it (Windows Terminal's
  split) and a bell are worth doing, later.

## Consequences

- An unseen question costs one minute and a sentence from the agent asking the owner, not ten minutes of refusals.
- A program that retries at once while the owner is away asks again each time; each question waits for one answer
  (the same question while it waits).
