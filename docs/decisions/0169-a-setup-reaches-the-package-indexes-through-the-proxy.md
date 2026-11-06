# 0169. A workspace's setup reaches only the package indexes, through the workspace's proxy, and runs nothing of its home but what it makes

- Status: Accepted (the audit of 2026-10-30); revises design 0004 §10, design 0024 §5 and design 0014 §4, and
  corrects what design 0015 §5 says a setup's container reaches
- Date: 2026-11-05
- Decided by: the audit's item on a folder's setup, as its spec asks (the workspace's network and proxy, a named set of
  package indexes, a clean home and pip set up by Clank alone, the question saying what runs)

## Context

- A workspace's setup (design 0004 §10) installs the folder's own software into `~/.venv` in the workspace's home, a
  Docker volume its agent writes too. It runs the folder's own install steps: `pip install -e .` builds the folder's
  package, which runs the folder's code (its build backend, a `setup.py`).
- The agent's own container reaches the internet only through Clank's proxy at the gateway, by the owner's allowances
  (design 0024, decision 0141), and every exchange is in the network log. The proxy knows whose a request is by the
  token in its URL, derived from the service's local token and the name it carries.
- What the setup's installers download: `python3 -m venv` takes pip from the image itself (Ubuntu's wheels), and pip
  then reads the Python Package Index, `pypi.org` for what there is and `files.pythonhosted.org` for the files; a
  package built from source fetches its build tools from the same two. Nothing else, unless a requirements file names
  another index or a git URL.
- A login shell reads the profile in the home, pip reads configuration files in the home and in the environment it
  runs, Python runs the `.pth` files of the site-packages it starts with, and git and setuptools read files in the home
  too. Everything in the home volume can have been written by the agent.

## Decision

- **The setup joins the workspace's own internal network and goes out only through the workspace's proxy.** Its
  container is told the proxy as the workspace's container is (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`),
  and the lowercase forms too, which curl and git read for plain HTTP. Before it runs, the workspace's network and the
  edge on it are put right as an opening does, and the gateway must run (else the setup is refused, saying so).
- **It has an identity of its own at the proxy**: the workspace's name with `.setup` after it (`paper.setup`), its
  token derived as a workspace's is. The gateway's routes carry it, with its hosts, only while the setup runs
  (`Workspaces.carry_setup`, `Gateway.set_setup`), so the identity reaches nothing before or after. A workspace's own
  allowances are never its setup's, and its setup's never its agent's.
- **What a setup reaches is the named set `setup`** in `config/network-sets.json` (design 0024 §5): `pypi.org` and
  `files.pythonhosted.org` as Clank writes it, the owner's to change. A file written before the set has none; Clank's
  default stands in then, saying so in the set's words, and the file is left as it is. `clank workspace sets` lists it
  with the others; it is never allowed to an agent (`clank workspace allow --set setup` is refused, naming `python`,
  and the folder page's `h` does not offer it).
- **A host not in the set is refused at once**, in words that name the set; it is never asked for (nobody waits at a
  setup), and dev mode does not lift it: dev mode opens the agent's internet, not a setup's. A private address is
  refused as always. Each exchange is in the network log under the setup's identity, and a workspace's log shows its
  setup's with its agent's.
- **It runs nothing of the home but what it makes.** The container runs `bash -c`, never a login shell. Its `HOME` is
  `/tmp/clank-setup-home`, a folder in the container's own files, made empty and removed with it; `PIP_CONFIG_FILE` is
  `/dev/null`, so pip reads no configuration file. Before the command, Clank removes `~/.venv` (a link as a link) and
  makes it afresh with the image's own Python in isolated mode (`/usr/bin/python3 -I -m venv
  --system-site-packages`); a step of these that fails ends the setup. `~/.venv` in the command is still the
  workspace's environment (`/home/agent/.venv`), so a command kept from before installs where the agent finds it.
- **The question says what runs**: the folder's own install steps, which can run code from the folder; that they reach
  only the package indexes (naming them), through Clank's proxy, each exchange in `clank network log`; and that
  `~/.venv` is made afresh first, with a clean home and pip set up by Clank alone. Each setup asks again, so a changed
  requirements file is installed only when asked for (unless told `--yes`, or given through the form, as before).

## Alternatives considered

- **The workspace's own identity at the proxy.** The setup would reach the agent's allowances, and a host it needs
  would be asked for as the agent's, in the agent's words. Refused: what a setup reaches should not depend on what the
  agent was allowed, nor the agent's on the setup.
- **The setup's identity always in the routes.** Simpler, but its token, given to the folder's code during a setup,
  would reach the package indexes whenever used. Carried only while it runs, it reaches nothing after.
- **The set `python` for the setup too.** One set fewer, but allowing the agent `pip install` and choosing what a setup
  reaches are different choices: the owner changing one should not change the other.
- **Keeping `~/.venv` and installing on top of it.** What the agent installed by itself would stay, but pip itself, the
  interpreter's links and the `.pth` files would be the home's, so the setup would run what was written there.
- **Rewriting no command.** A command kept from before (Clank's own proposal, kept by the folder page's form) names
  `~/.venv`; with the clean `HOME` it would install into the container's own files and be lost while the setup said
  it was installed. `~/.venv` is read as the workspace's environment instead, `~` alone anything else.
- **Asking the owner for a host the setup needs.** The setup runs unattended, often with `--yes`; a held connection
  would stall it. The set is the place to add a host, before the setup runs again.
- **Lifting the set in dev mode.** The question would then say something untrue while dev mode is on.

## Consequences

- A setup reaches the package indexes alone: one whose requirements name another index or a git URL fails until the
  owner adds that host to the set `setup`; the failure's words say so, and `clank network log` shows the refusal.
- Each setup reinstalls the folder's software into a new `~/.venv`: what the agent installed in it by itself is gone,
  and the setup takes as long as a first one (no pip cache is kept in the clean home). An agent running from
  `~/.venv` during a setup finds it empty until the setup ends.
- A setup needs the gateway running, as the agent does; the service keeps it running unless its settings say not to.
- The folder's code still runs in the setup, with the package indexes reachable, as the question says.
