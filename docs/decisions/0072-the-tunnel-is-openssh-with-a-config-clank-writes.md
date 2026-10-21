# 0072. The tunnel is the owner's own OpenSSH, run with a configuration file Clank writes

- Status: Proposed
- Date: 2026-10-18
- Decided by: Claude, with [design 0015](../design/0015-endpoints.md) §5, from the research of 2026-10-18 and its
  review of 2026-10-19; the owner approves or changes it with the design

## Context

- Design 0001 §2 and §7.6 (approved) put an endpoint behind an SSH tunnel Clank opens: through a login host to the
  compute node and port of a server on a cluster. A cluster's documentation gives exactly that tunnel, `ssh -NL <local
  port>:<node>:<port> <user>@<login host>`, with `-J <user>@<jump host>` added from outside the cluster's network (its
  research-computing pages; the real names live in the owner's local configuration only).
- Clank must open it unattended and keep it honest: never prompt (`BatchMode`), end at once when the forward cannot be
  set up (`ExitOnForwardFailure`), notice a connection that died without closing (`ServerAliveInterval`,
  `ServerAliveCountMax`), and never accept a host key it does not know (`StrictHostKeyChecking`).
- OpenSSH applies options given with `-o` to the destination only. Its manual, at `-J`: "configuration directives
  supplied on the command-line generally apply to the destination host and not any specified jump hosts. Use
  ~/.ssh/config to specify configuration for jump hosts" (https://man.openbsd.org/ssh). So `ssh -o BatchMode=yes -J
  ...` can still prompt on the jump host, where nobody sees it.
- `-F <file>` replaces the owner's own configuration file, and the system-wide one is then ignored (the same manual).
- A jump host can be named two ways. With `ProxyJump`, ssh builds the jump's command itself: current OpenSSH adds the
  same `-F <file>` to it (openssh-portable's `ssh.c`), but writes that path, and its own, without quotes, so a
  `CLANK_HOME` or an `ssh` path holding a space (common on Windows: user names, `Program Files`) breaks the jump; and
  which versions add `-F` is one more thing to depend on. With `ProxyCommand`, the configuration names the jump's
  command whole.
- From OpenSSH 8.5, `UpdateHostKeys` is on by default when the configuration does not override the known hosts files,
  so ssh may add a host's other keys to the owner's `known_hosts` (ssh_config(5)).
- ssh reports a refused login with every method the server would still accept, as in
  `Permission denied (publickey,keyboard-interactive)`.
- Every system Clank runs on has OpenSSH's client: Linux, macOS, and Windows (in `C:\Windows\System32\OpenSSH\`). The
  owner's key, agent and `known_hosts` already work with it (T0, design 0015 §15).
- Clank's engines and its gateway are processes of their own, so a restart of the service cuts nothing in flight
  (design 0002 §1); a tunnel should be one too. The local host already starts, identifies and adopts such a process
  (`clank/components/runtime/hosts/local.py:48-102`, `clank/components/runtime/watching.py:61-89`).
- AGENTS.md: no new dependency without a decision that says why it is worth it.

## Decision

- The tunnel is the owner's own `ssh` (the first on the PATH, or the program the endpoint names), run by the local host
  as a process of its own, as an engine is. Inside Clank the program is a list of arguments, as an install's is.
- Before each start, Clank writes `CLANK_HOME/state/tunnels/<endpoint>.conf` from the endpoint's record, readable and
  writable by the owner only: a `Host` block for each host (the login host, the jump host, and the node when the
  tunnel ends there), each with `BatchMode yes`, `ConnectTimeout 10`, `ServerAliveInterval 15`,
  `ServerAliveCountMax 3`, `StrictHostKeyChecking yes`, `UpdateHostKeys no` and `ExitOnForwardFailure yes`; an
  `IdentityFile`, with `IdentitiesOnly yes`, only when the endpoint names a key file.
- Each host is reached through the one before it by `ProxyCommand "<the same ssh, by its full path>" -F "<this file>"
  -W [%h]:%p <that host's alias>`. Clank quotes both paths for the shell ssh runs the command with, doubles each `%`,
  and refuses a path it cannot quote, saying so.
- It runs `ssh -F <that file> -N -T -L 127.0.0.1:<slot port>:<node>:<port> clank-<endpoint>`, or, when the tunnel
  ends at the node, `-L 127.0.0.1:<slot port>:127.0.0.1:<port> clank-<endpoint>-node`: the forward listens on the
  loopback only, at the slot's own port. Nothing is passed with `-o`.
- The owner's `~/.ssh/config` is not read (the file says everything ssh needs), but their keys, agent and `known_hosts`
  are used as ssh uses them. Clank adds no key, never writes `known_hosts`, and never turns host key checking off.
- ssh's refusals are read by their words, and a refused login by its list of methods (design 0015 §5).
- It is written for the OpenSSH versions recorded in `tests/fixtures/openssh/` (Windows' own and a Linux one, the
  Pi's): the check names the version in use, and says when it is older than the oldest recorded.
- No SSH library: no new dependency.

## Alternatives considered

- **`-o` options on the command line, with `-J`.** The jump host would get none of them: no `BatchMode` (a prompt no
  one sees), no keepalive.
- **`ProxyJump`, with the same `-F` file.** Shorter to write, and current OpenSSH passes the file on to the jump. But
  ssh writes both paths unquoted, so a space in either breaks the jump, and Clank would depend on the versions that
  pass the file.
- **A `Host` entry the owner writes in their own `~/.ssh/config`.** Clank would depend on a file it does not own, and
  the tunnel's settings would not be visible or changeable in Clank (principle 3, transparency).
- **An SSH library (Paramiko, AsyncSSH).** A new dependency, which would redo what OpenSSH already does for the owner
  (the agent, jump hosts, known hosts, key formats), and a tunnel inside the service's own process, cut by its
  restart.
- **autossh.** Another program to install on every system; the runtime's watcher does its work (design 0015 §7).

## Consequences

- The tunnel outlives a restart of the service and is adopted by its identity; a dropped one is reopened by the
  watcher (design 0015 §7).
- `ssh -G -F <file> <alias>` shows exactly what ssh will use, for the check and for the owner (design 0015 §11).
- What ssh prints when it refuses is read into what to do, from its own words recorded on Windows and Linux (design
  0015 §5, §14).
- Unattended needs a login that accepts a key without a second factor. If T0 finds that it does not, the fallback is a
  tunnel the owner opens, reached as a URL endpoint on the loopback (design 0015 §5).
- The file holds user and host names, never a key, and lives in the owner's `CLANK_HOME`, never in the repository.
- Tests run a fake `ssh` as a list of arguments, so it runs on Windows too (design 0015 §14); how Windows' own
  OpenSSH runs the `ProxyCommand` line is measured in T1.
