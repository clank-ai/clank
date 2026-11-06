# 0168. Your MCP servers with secrets go only to the workspaces you name, their values in OpenCode's environment alone

- Status: Accepted (the audit of 2026-10-30); revises design 0002 §2.8, design 0004 §10 and design 0016 §9
- Date: 2026-11-05
- Decided by: the audit's item on the owner's MCP servers, as its spec asks (opt-in per workspace, values by name)

## Context

- Your own MCP servers (`clank mcp add`) keep the values of their environment variables and headers as secrets, one
  file each in `CLANK_HOME/secrets` (design 0002 §2.8). Such a value is usually a key to a service of yours: a
  token for GitHub, a database's password.
- An MCP server runs beside the agent, in the workspace's container, started by OpenCode. OpenCode gives every local
  MCP server its own whole environment, then the server's entry (`environment`) over it, and the agent's shell
  commands run with that same environment. Whatever a server is given, the agent can read; and what the agent reads,
  a cloud model reads too when the workspace uses one.
- OpenCode reads `{env:NAME}` in its configuration as the variable `NAME` of its own environment: it puts the
  variable's text into the file's text before it reads the file as JSON (its `ConfigVariable.substitute`, read in its
  1.18 binary; local MCP servers are started with its whole environment, its `MCP.connectLocal`).
- `docker exec --env NAME` (a name alone) takes the value from the environment of the `docker` process itself, so a
  value need not be on a command line, which every program on the computer can read.

## Decision

- **A server of yours that carries secret values is given only to the workspaces you name for it.** The workspace's
  record lists them (`mcp_secrets` in `config/workspaces/<name>.json`, "Your MCP servers with secrets it gets");
  `clank mcp allow NAME` in the folder, `m` on the folder's page and `s` on the MCP servers page add one, and `clank mcp
  hold NAME` (or the same keys) take it away. A server of yours without secrets is given to every workspace unless
  held back (`mcp_off`), as before. A server marked local only is still never given to a workspace that may use the
  cloud.
- **Giving one to a workspace that may use a cloud model asks first**, in the service's words: its agent can read the
  server's values, and a model at a provider will be able to read what the agent reads, those values too. The service
  refuses without that confirmation (`409 unconfirmed`); `clank mcp allow` asks in the terminal (`--yes` answers it),
  and the console asks in a window. A workspace whose question whether it may use the cloud model waits is asked the
  same way, since its answer may allow it.
- **Allowing a workspace the cloud names first each such server its agent gets** (design 0016 §9), with the names of
  its values: its agent can read them, and with the cloud model a model at a provider will be able to read them too.
  The question asked once says so in its detail, and so do the words `u` on the folder's page and `clank workspace allow
  FOLDER --cloud` show before they change the bound (`cloud_confirm`); a server marked local only, which never goes
  with the cloud, is not named. So whichever comes first, the server or the cloud, the owner is asked knowing the
  values can reach a model at a provider. The agents component, which knows which servers a workspace gets, tells the
  workspaces' service how to read them as it is built (`on_carried`), so no component uses the other in a cycle
  (decision 0019).
- **The values reach the agent in OpenCode's own environment, never in a file.** OpenCode's configuration names a
  variable for each value (`"KEY": "{env:CLANK_MCP_<SERVER>__KEY}"`); the variable's text is the value as JSON writes
  it inside a string (quotes, backslashes and line breaks escaped, and each `{` written as JSON's escape for it), so
  OpenCode reads back the exact value and finds no other reference in it. The variables go to `docker exec` by name
  alone, and their values in the environment of the process that runs it: the service's for OpenCode without a
  terminal (the bridge's input), the client's for a terminal (`agents/prepare` answers `argv` and `env`; `clank work`,
  `clank flow`, the console and VS Code run the command with `env` over their own environment).
- **Every `docker exec` Clank makes names each variable alone**, its value in the environment of the process that runs
  it, whatever the variable (the agent's thread counts too).
- **A check starts such a server in a workspace's container only when that workspace gets it** (its record names
  it): in another workspace the check is refused before any value is read, saying how to check it, and the MCP servers
  page's `c` checks it on this computer instead.
- **A running OpenCode that does not know such a server is not given it live**: no entry, so no value, is sent over
  the bridge; it is given at the agent's next start, and the answer says so.
- **Adding a server with secrets says so**: `clank mcp add` and the console's form say, in the service's words (the
  server's `secrets_said`), that its values go to no workspace until you give it to one, and that the agent of every
  workspace you give it to can read them.

## Alternatives considered

- **Keep giving every server to every workspace, values in the configuration file**: the values sat in the home volume
  of every workspace, whether its work needed the server or not.
- **Values in a file of their own in the container, read by reference (`{file:...}`)**: still a file holding the
  value in the container's home, which outlives the agent's run.
- **No `environment` entry at all, the value under its own name in OpenCode's environment**: OpenCode passes its whole
  environment to every server anyway, but two servers of yours wanting the same variable (`API_KEY`) with different
  values could not both be given; a name of Clank's own per server and variable keeps them apart.
- **Add a server with secrets to a running OpenCode through its API, values in the entry**: the values would travel
  outside OpenCode's environment, and an entry so added is not what OpenCode's configuration says; at the next start
  it is given like the others.
- **Hold back a server with secrets from a cloud workspace altogether**: some servers are meant for exactly that work;
  the owner decides, told what it means.
- **Take such servers away from a workspace when it is allowed the cloud, to be given again after**: two steps where
  one, the cloud's own question naming them, tells the owner the same and lets the owner choose there.

## Consequences

- A server of yours with secrets that every workspace used to get is now given to none until you name a workspace for
  it: `clank mcp allow NAME` in each folder that needs it.
- The clients that start the agent's window receive the values of the servers given to that workspace, in the answer
  of `agents/prepare`, to pass them to `docker exec`'s environment; the route answers the owner's own clients alone (the
  gateway forwards it to no agent), and nothing Clank records holds the values.
- The agent of a workspace can read the values of the servers given to it (they are in its environment, as in its
  servers'); SECURITY.md says so.
- An agent program other than OpenCode needs its own way to read a value from its environment before it can be given
  such a server (`by_reference` of its adapter).
