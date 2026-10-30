# 0150. Clank takes the docker group at once, so nobody logs out and in for it

- Status: Accepted (the owner's instruction of 2026-10-29, after the first install on Linux: "in the step where it is
  telling me to log out and log back in, I am not exactly sure what this is asking me to do … let's try and make sure
  we are automating away these steps by just asking permissions"); revises design 0028 §3, §4 and §5
- Date: 2026-10-29

## Context

- On Linux, the account must be in the `docker` group to use Docker Engine without sudo. The installer and
  `clank setup` add it, asking first (`sudo usermod -aG docker <account>`).
- A process keeps the groups it started with, so the group reaches only programs started after the next login. Until
  then the installer told the person to log out and in once, and `clank setup` stopped there. The owner did not know
  what that step meant, nor why it was needed.
- The system's own `sg docker -c <command>` (shadow-utils, installed on every distribution the installer supports)
  runs a command with a group the account is in, asking nothing. The installer already checked Docker through it after
  joining.
- Everything Clank does with Docker goes through the `clank` command or the service it starts: the service's calls,
  and the `docker exec` that `clank work` and This folder run in the terminal.

## Decision

- **Every `clank` command takes the group itself.** On Linux, when the system lists the account in the docker group
  but the process lacks it, the command's entry runs the same command again through `sg docker`, with the same
  arguments, the same terminal and environment (`clank.cli.dockergroup`). The service it starts, and every `docker`
  command they run, have the group from then on. It is done once (`CLANK_DOCKER_GROUP=1` in the command run again),
  and not at all where `sg` is missing, on Windows, or for a process that has the group.
- **`clank setup` goes on after joining.** Once the join command succeeded, the setup runs itself again through the
  group and carries on with the next item, instead of stopping for a log out.
- **A service that started before the join is restarted.** The checklist's "Docker usable by this account" item, for
  a service that keeps its old groups, offers to restart it; `clank setup` stops it and starts it again, with the
  group, on a yes.
- **The installer says so.** After joining, it says that Clank uses the group at once and that the person's own
  `docker` commands get it at their next login; it then offers to run `clank setup` straight away, which asks before
  each step.
- Where `sg` is missing, the words stay as before: log out and in once.

## Alternatives considered

- **Keep the log out and in**: the owner found it unclear, and it is a step a computer can do.
- **`newgrp docker`**: it starts a new shell, and so cannot help a command that is already running.
- **An ACL on Docker's socket for this account**: it needs root again, and Docker's restart drops it.
- **Restarting the person's session for them**: too much to do behind someone's back.

## Consequences

- From the installer to the agent's first answer, nobody logs out and in, unless `sg` is missing.
- A `clank` command between the join and the next login starts one shell more (`sg`), which takes milliseconds.
- `docker` typed by the person keeps needing the next login, as Docker's own documentation says; the installer and
  the setup say so.
- The group's rights are what the person agreed to when they joined it. Clank only uses them sooner.
