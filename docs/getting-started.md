# Getting started

From nothing to an AI coding agent working in one of your folders: install Clank, add a model, open a folder. The
quickest path uses a cloud model through an API key (OpenRouter) and needs no GPU; a model on your own GPU is the other
path (step 3b). Written for Windows first; macOS and Linux notes are at the end.

## 1. What you need

| | Needed for | Notes |
| --- | --- | --- |
| Windows 10 or 11, with WSL 2 | everything | Docker Desktop turns WSL 2 on when it installs |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | the agent's workspaces | each folder you work in gets a container of its own; the first one downloads about a gigabyte |
| [uv](https://docs.astral.sh/uv/) | installing Clank | it brings Python 3.12 by itself |
| [Git](https://git-scm.com/) | getting Clank | |
| An [OpenRouter](https://openrouter.ai/) account and API key | the cloud path | free models exist; paid ones need credits |
| An NVIDIA GPU (16 GB is comfortable) | the local path only | not needed for the cloud path |
| [VS Code](https://code.visualstudio.com/) and [Node.js](https://nodejs.org/) 22 or newer | Clank's VS Code window (optional) | Node builds Clank's extension once (step 2b) |

## 2. Install

### The quick way: one line

In PowerShell:

```
irm https://clank-ai.github.io/install.ps1 | iex
```

It says each step as it takes it:

1. **uv**: uses the one you have, or installs it with Astral's own installer.
2. **Git**: Clank is downloaded with it. If it is missing, the installer offers `winget install --id Git.Git -e`
   and asks first.
3. **Docker Desktop**: if it is missing, the installer says how to get it and offers
   `winget install --id Docker.DockerDesktop -e`, asking first (it needs administrator rights and may need a restart).
   It never installs Docker without your yes; Clank itself installs without it.
4. **Clank**: its latest release (the installer says which), with `uv tool install`, then `uv tool update-shell`
   so `clank` is on your path.
5. **`clank doctor`**, which checks the computer and changes nothing.

It never asks for a key. Set `CLANK_NO_MODIFY_PATH=1` first to leave your path alone, or `CLANK_VERSION` to a
release tag (or `main`) to install that instead of the latest release. The script is short and readable:
[install.ps1](https://clank-ai.github.io/install.ps1), and on macOS and Linux
[install.sh](https://clank-ai.github.io/install.sh). Then open Docker Desktop once if it is new, accept its terms
and let it finish starting, and open a new PowerShell so `clank` is found.

### Or by hand, from a clone

Install from a clone if you want Clank's VS Code window (step 2b), which is built from the clone. In PowerShell:

```
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id Docker.DockerDesktop -e
```

Then open Docker Desktop once, accept its terms and let it finish starting. Close PowerShell and open a new one, so the
new programs are on its path.

Get Clank and install it:

```
git clone https://github.com/clank-ai/clank
cd clank
uv tool install --editable .
uv tool update-shell
```

Open a new PowerShell once more, then check the computer:

```
clank doctor
```

It changes nothing; it says what is ready and what is missing (Docker, WSL, a GPU), each with what to do.

## 2b. Build the VS Code extension (optional)

Clank's VS Code window (`c` on **This folder**, or `clank code`) shows the agent beside your files, its changes for
you to review and figures to mark up. It needs Clank's extension, built once from the clone (and again after an update
that changes it); until then, `c` says the extension is not built. It needs Clank installed by hand from a clone
(step 2, the second way): the one-line installer's Clank does not carry the extension's sources. In PowerShell:

```
winget install --id Microsoft.VisualStudioCode -e
winget install --id OpenJS.NodeJS.LTS -e
```

Open a new PowerShell, then in the `clank` folder:

```
cd vscode
npm ci
npm run build
cd ..
uv run --no-dev python -m tools.vsix
```

The last command writes `vscode\clank-<version>.vsix` (the extension's own version, 0.10.4 now). Clank's VS Code window
installs it by itself; to have it in your usual VS Code too:

```
code --install-extension vscode\clank-0.10.4.vsix
```

## 3a. Add a cloud model (OpenRouter)

1. Make an API key at [openrouter.ai/keys](https://openrouter.ai/keys). Add credits if you want paid models.
2. Type `clank`. With no model set up, the console opens on **Add a model** (later: F12 in the menu, or `a` on
   **Providers and models**).
3. Press `c` for **Cloud**, then Enter on **OpenRouter**.
4. Read the **agreement**: what goes to OpenRouter (the prompts and the files the agent reads in a workspace you allow),
   what never goes (Notion, and MCP servers marked local: Space marks or unmarks one), and the data policy (`o`).
   Press `y` to agree; `n` writes nothing.
5. Paste the key into the hidden field and press Enter. It is checked with OpenRouter once and kept in Clank's
   secrets folder only; the console shows its last four characters, never the rest.
6. Pick a model from the live list: `/` searches, `s` sorts, `f` shows only the free ones. Enter picks it.
7. Check its settings (filled in for you) and press Enter. Clank sends one short test request and shows the answer
   and what it cost.
8. **Ready.** Clank says whether Docker is running (`s` starts it); Enter takes you to **This folder**.

What it costs shows on the header, Home, Requests (F7), the Monitor and `clank cost`. You can set a daily or monthly
limit (`L` anywhere, or `clank cost limit`); when it is reached, cloud requests pause until you raise it.

## 3b. Or a model on your own GPU

Clank runs local models with llama.cpp or KVMem (an engine that keeps a long context partly in system memory). On
Windows they run in WSL. This path is not one step yet: the engine is built in WSL and the model file downloaded, then
a **preset** (the model with its settings) is loaded into the main slot. Start from **Add a model** → `l` **Local**:
it lists the presets with what each needs and walks you through each step, asking first. One setup worth building
again, with every setting and why, is written up in [docs/models/](models/README.md).

## 4. Work in a folder

1. Open a terminal in the folder you want to work in and type `clank`. The console opens on **This folder** (F4).
2. It lists what working here needs: Docker, the folder's workspace, its software, a model, the gateway. `g` does
   every step that is not done. The first workspace builds Clank's sandbox image, which takes a few minutes.
3. With a cloud model, Clank asks once whether this folder's work may go to OpenRouter. Answer `y`, or keep the folder
   on your computer only. `u` changes it later.
4. `a` starts **OpenCode** (the agent) in this terminal; leave it with `/exit` and the console comes back. Or `c`
   opens the folder in VS Code with OpenCode beside your files.
5. In **review** mode (the default) the agent asks before it changes a file: answer under **Waiting for you** (`y`,
   `n`, `v` shows the change) or in VS Code. `r` switches to **auto**, where it changes files without asking.

Then look around: the **Monitor** (F10) shows what the agent does and what fills its context window, and lets you
stop, pause, guide or undo it; **Flows** (F10's Flow view, `n`) split a larger piece of work into steps, each a fresh
session. [docs/console.md](console.md) explains every page and key.

### Let the agent reach the internet

A workspace's container reaches nothing but Clank by itself. When the agent needs a host (a package index, a
paper's site, a documentation site), allow that host for that workspace, and only it: `clank workspace allow
FOLDER --host pypi.org --host .arxiv.org` (a name, or a suffix starting with a dot for a site and everything under
it; `--no-host` takes one back), or a named set with one word: `--set papers` (arXiv, Semantic Scholar, Crossref,
OpenAlex, DOI), `--set python`, `--set code`, `--set data`, `--set docs` (`clank workspace sets` lists them; the file
`config/network-sets.json` in your Clank home is yours to change). The agent's requests go through Clank's proxy, which lets them out to the hosts
allowed; a host not allowed is asked for: the request waits up to a minute while the question shows under
**Waiting for you** (`y` allows it always for the workspace, `o` once, `n` refuses it, and it is not asked again
for ten minutes); refused, the agent reads why in plain words. Private addresses (your machine, your network) are
never reached. Every exchange is logged in `logs/network/` by host, status, bytes and time, never by content. A
workspace made before this gets the proxy when it is next stopped and opened.

### Boards: lay out figures with the agent

In VS Code, a **board** is a canvas you share with the agent: a `.board` file in the folder ([design
0022](design/0022-boards.md)). Make one with **Clank: New board**, or ask the agent ("make a board with the two plots
side by side and the fit's equation under them"). The agent's container has Python's scientific packages (NumPy,
SciPy, pandas, Matplotlib, SymPy), so it makes the plots itself.

- **Figures** are the folder's images, drawn again when a script writes them again. Drop one from the Explorer or
  paste one.
- **LaTeX**: math is drawn at once; TikZ, pgfplots and tables are compiled with the folder's TeX (`clank latex setup`
  adds it).
- **Ask the agent**: select items and ask about them; draw a **slot** and press **Fill** for the agent to make that
  figure; **pin** comments and **Send pins**.
- **Export** a frame as one figure: PDF for `\includegraphics`, PNG or SVG, beside the board. Kept, it is made again
  each time the frame changes, so your paper always shows the latest layout.

## 4b. Work from another computer, over SSH

With a model on your GPU, every window the PC draws slows the model down. Working from a laptop instead, with VS Code
on the laptop connected to the PC, leaves the PC's screen out of it
([design 0018 §8](design/0018-clank-code.md#8-vs-code-on-another-computer)).

1. **On the PC, once:** turn on Windows' OpenSSH server (Settings → System → Optional features → OpenSSH Server, then
   start the `sshd` service and set it to start automatically) and add your laptop's public key to it, as
   [Microsoft's guide](https://learn.microsoft.com/windows-server/administration/openssh/openssh_install_firstuse)
   says. Build Clank's extension there (step 2b), and start Clank's service at the PC itself (`clank serve
   --background`): started over SSH, it runs where it cannot use Docker's sign-in.
2. **On the laptop:** install VS Code and Microsoft's Remote-SSH extension; nothing of Clank. Connect to the PC (F1,
   **Remote-SSH: Connect to Host**).
3. **In that window**, open a terminal (it runs on the PC), go to your folder and type `clank`. `c` on **This folder**
   (or `clank code`) gets everything ready, then opens the folder in a new VS Code window on the laptop, connected to
   the PC, with OpenCode beside your files. The first time, Clank installs its extension and the window's others in
   VS Code's server on the PC, and adds its settings to that server's machine settings.
4. **Lock the PC** (Windows+L) or turn its screens off: it then draws nothing for your work.
5. **Ready after a restart:** `clank autostart on` starts Clank's service, and Docker through it, when you sign in
   to Windows (Task Manager's Startup apps lists it as Clank; `clank autostart off` removes it). Over SSH they cannot
   be started, so after a Windows update's restart the PC needs you to sign in once at it.

From a plain SSH terminal (no VS Code), `c` opens nothing: a VS Code window there would open on the PC's own screen.
Clank says the command to run on the laptop instead, `code --folder-uri "vscode-remote://ssh-remote+HOST/c:/..."`.
HOST is the address you connected to, or the name in `ssh_host` of `config/vscode.json` (the name your laptop's SSH
configuration gives the PC). If Clank's extension is also installed in the laptop's own VS Code, add
`"remote.extensionKind": {"clank.clank": ["workspace"]}` to the laptop's settings, so it runs on the PC's side, where
Clank is.

## 4c. Clank on your iPhone

Clank's phone app shows what the model does and what waits for you, and answers from your pocket: a permission, a
question, a flow's gate, a new task ([design 0025](design/0025-clank-for-iphone.md)). It reaches the PC only
through your tailnet; nothing of it goes through anyone else's server, and the app itself is served by the PC.

1. **Tailscale on both.** Install [Tailscale](https://tailscale.com/download) on the PC and on the iPhone, signed
   in to the same account. Clank publishes its phone listener on the tailnet only, never to the internet.
2. **Turn it on, on the PC:** `clank remote on`, or `x` on the console's Phone page (F9). `clank remote status`
   says its address, and why not when it cannot listen (Tailscale not signed in, Funnel on for its port).
3. **Pair the iPhone:** on the console's Phone page press `p` (or run `clank remote pair`). A QR code shows, with
   its link and a code under it. Scan the QR with the iPhone's camera: the page that opens pairs the phone and
   shows the steps to add Clank to the Home Screen (Share, then Add to Home Screen). Open it from its icon: the
   app runs full screen, live on one stream from the PC, and stays paired for as long as it is used (thirty days
   unused, and it asks to pair again). Without a camera at hand, type the code on the page instead.
4. **When the PC cannot be reached,** the app says so, shows the last it knew and tries again on its own. Check
   that Tailscale on the iPhone says Connected, and that the PC is awake.

**If the page does not load** (Safari waits, then says it cannot connect to the server):

1. **Tailscale on the iPhone says Connected**, signed in to the same Tailscale account as the PC.
2. **Use Tailscale DNS settings is on** in the iPhone's Tailscale app, so the iPhone finds the PC's name through your
   tailnet.
3. **iCloud Private Relay is off** on the iPhone (Settings, your name, iCloud, Private Relay): with it on, Safari asks
   Apple's servers for the PC's name instead. That matters when Tailscale Funnel is on for any port of the PC: the name
   then also has a public address, Tailscale's relay, which does not carry the phone page's port. Turn Airplane Mode on
   and off afterwards to clear the iPhone's DNS cache. Or, if nothing on the PC needs Funnel, turn it off there
   (`tailscale funnel status` shows what it publishes).
4. **Open the link in Safari** itself, the one under the QR.
5. **Read the console's Phone page (F9)**: under the QR it says how the phone reaches the PC, checked from the PC: your
   phones on the tailnet (online, or when last seen), whether anything from the phone reached Clank today and why it
   was refused, Funnel, and the PC's side, each with what to do; `r` checks again. `clank remote status` and
   `clank doctor` say the same.
6. **Make a new QR** with `p` (a code works once, for fifteen minutes), and scan it.

The console's Phone page lists the paired devices and everything each exchanged with the PC (Enter); `d` revokes
one. The phone keeps only its token and the last summary, names and numbers. The app's Flows and session screens,
its notifications and its settings come with design 0025's next steps.

## 5. Updating

See what is newer, then update, the way Clank was installed:

```
clank update --check
clank update
```

`clank update --check` changes nothing: it says how Clank was installed (the installer's release, or a clone), what is
newer (the latest release on GitHub, or the commits your clone's branch is behind), and what it asked to know it
(GitHub's API, or your clone's own remote). `clank update` then installs the newer release as the installer does, or
pulls your clone (refused while it has changes of its own). When the tool itself must be installed again, Clank stops
its service and gateway, finishes in a small helper after the command ends, and starts the service again; each step
goes to `~/.clank/logs/update.log`. `clank update --dry-run` says each step without doing it. Your settings and
everything in `~/.clank` stay as they are.

Run it at the computer itself, not over SSH (started from an SSH session, the service runs where it cannot use
Docker's sign-in). If the VS Code extension changed, build it again (step 2b). If Clank then says a workspace's
container uses an older sandbox image, reopen that workspace: **Workspaces** (F6), `x` to stop it, then `o` to open it
again.

## 6. Troubleshooting

| What you see | What to do |
| --- | --- |
| "Docker is stopped" | Start Docker Desktop, or `clank docker start` |
| A workspace says its container uses an older sandbox image | Reopen it: F6, `x`, then `o` |
| F10 opens your terminal's menu instead of the Monitor | `clank console --page monitor` |
| The key is refused (401) | Make a new key at OpenRouter and add it again (`clank endpoint key openrouter`) |
| "No credits" (402) | Add credits at OpenRouter, or pick a free model |
| `clank` is not found | Open a new terminal after `uv tool update-shell` |

## 7. Uninstalling

```
clank stop
uv tool uninstall clank
```

Clank's own folder, `%USERPROFILE%\.clank`, keeps your settings, records and keys: delete it to remove those too.
Workspace containers are removed from **Workspaces** (F6, `d`) before that, or from Docker Desktop. If the installer
installed uv and nothing else uses it,
[uv's guide](https://docs.astral.sh/uv/getting-started/installation/#uninstallation) says how to remove it.

## macOS and Linux

Clank's console, the cloud path and its commands are the same. The one-line installer:

```
curl -fsSL https://clank-ai.github.io/install.sh | sh
```

It installs uv if it is missing, checks Git (and offers your package manager's command for it, asking first) and
Docker (Docker Desktop on macOS; [Docker Engine](https://docs.docker.com/engine/install/) on Linux, which it never
installs), installs Clank's latest release and runs `clank doctor`; run it again to update. Or install uv, Git and
Docker the way your system does, then follow step 2 from `git clone`. Neither system has been tested beyond the
installer.
On Linux, the gateway also listens on a socket in a folder of its own, `~/.cache/clank/<home id>` (yours alone;
`clank gateway status` names it), and with Docker Engine the agent's container reaches the model through it. Clank's
adapter for Docker Engine itself is still being built ([design 0014](design/0014-linux-and-small-machines.md)), so
until it comes, no workspace opens there. Uninstalling on Linux, delete `~/.clank` and `~/.cache/clank` too.
