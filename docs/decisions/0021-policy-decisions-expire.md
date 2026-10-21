# 0021. Policy decisions expire and name the policy's revision; the riskiest are made at the moment of use

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
Enforcement points (the edge, the tool hub, the gateway) ask the service for policy decisions. To stay fast, and to
keep work going while the service restarts, they keep the decisions that allowed something. A kept decision can
outlive the grant that justified it, or the mode it was made under; the outside review of 2026-10-11 (design 0002)
asked what revoking a grant actually stops.

## Decision
Each policy decision carries the policy's revision and an expiry, and an enforcement point keeps it only until either
changes. Switching a mode, revoking a grant or editing a rule makes a new revision, which the service announces to every
enforcement point at once. Pushes (`git.push`), files sent to the user (`file.send`), secrets (`secret.use`) and model
requests to a third party's provider (`model.send`) are decided at the moment of use and never kept. While the service
is down, enforcement points finish what is in flight, keep their unexpired decisions, and refuse whatever must be
decided at the moment of use.

## Alternatives considered
- **Keep an allowed decision until its grant ends.** A revoked grant or a stricter mode would not reach enforcement
  points in time.
- **Ask the service for every action.** The simplest rule, but every model request and every connection would wait on
  the service, and all of them would stop while it restarts.

## Consequences
- Revoking a grant or switching a mode takes effect at once (tested in M7).
- While the service restarts, pushes, files sent and requests to a third party's model are refused for a moment.
- How long a decision is kept is a setting.
