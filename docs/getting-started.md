# Getting started

From nothing to an AI coding agent working in one of your folders: install Clank, add a model, open a folder. Clank
runs the model one of three ways:

- **In the cloud, through an API key** (OpenRouter): no GPU needed, each request paid and shown. The quickest start.
- **On your own GPU** (an NVIDIA card): nothing paid per request; an engine and a model file to set up.
- **Both**: a model on your GPU for most work, a frontier model in the cloud when it helps.

Clank runs on Windows, macOS and Linux. Where a step differs by system, it says so, with a block for each: open
yours. Every step says what it does before it does it, and asks before it installs anything.

## 1. What you need

| | Windows | macOS | Linux |
| --- | --- | --- | --- |
| The system | Windows 10 (22H2) or 11, 64-bit | a macOS that [Docker Desktop supports](https://docs.docker.com/desktop/setup/install/mac-install/) | 64-bit x86 with systemd: Ubuntu 22.04 or 24.04, Debian 12, Fedora, RHEL 9 or its kin (Rocky, Alma), or Arch |
| Docker, for the agent's workspaces | Docker Desktop, with WSL 2 | Docker Desktop | Docker Engine, from Docker's own packages (not the snap) |
| uv and Git, to install Clank | the installer gets them | the installer gets them | the installer gets them |
| For a cloud model | an [OpenRouter](https://openrouter.ai/) account and key | the same | the same |
| For a model on your GPU | an NVIDIA GPU (16 GB is comfortable), in WSL 2 | not possible: a Mac has no NVIDIA GPU | an NVIDIA GPU (16 GB is comfortable) and its driver |
| Disk | about 3 GB, and 10 to 15 GB more for a local model | about 3 GB | about 3 GB, and 10 to 15 GB more for a local model |

The installer installs Docker for you if it is missing, asking first (step 2). Optional: [VS Code](https://code.visualstudio.com/)
for Clank's VS Code window (step 2b), and [Tailscale](https://tailscale.com/download) for Clank on your iPhone (step 5c).

## 2. Install

### The one line

<details open>
<summary><b>Windows</b></summary>

In PowerShell (an ordinary one, not as administrator):

```
irm https://clank-ai.github.io/install.ps1 | iex
```

</details>

<details>
<summary><b>macOS and Linux</b></summary>

In a terminal:

```
curl -fsSL https://clank-ai.github.io/install.sh | sh
```

To see first what it would do, without changing anything:

```
curl -fsSL https://clank-ai.github.io/install.sh | CLANK_DRY_RUN=1 sh
```

</details>

The installer is a short script you can read first: [install.ps1](https://clank-ai.github.io/install.ps1),
[install.sh](https://clank-ai.github.io/install.sh). It never asks for a key, and you can run it again at any time: it
updates Clank and repairs what is missing.

### What it asks, and what to answer

It works in five numbered steps, says each before it takes it, and shows every command before it runs one. Answer `y`
to go on; anything else skips that step and says how to do it later.

<details>
<summary><b>Windows</b></summary>

1. **uv** (it installs Clank and the Python it runs on): the one you have, or Astral's own installer.
2. **Git** (Clank is downloaded with it): if it is missing, it offers `winget install --id Git.Git -e`.
3. **Docker Desktop**: if it is missing, it offers `winget install --id Docker.DockerDesktop -e`. Windows then asks
   for administrator rights (answer yes), and Docker Desktop's installer may turn WSL 2 on and ask to restart.
   Restart, and run the installer again: it goes on where it stopped. Then it offers to start Docker Desktop and
   waits for it (up to five minutes): the first time, Docker Desktop shows its terms in its own window; accept them.
4. **Clank**: its latest release, with `uv tool install`, then `uv tool update-shell` so `clank` is on your path.
5. **The check**: `clank doctor` says what is ready and what is not, each with what to do (step 3).

</details>

<details>
<summary><b>macOS</b></summary>

1. **uv**: the one you have, or Astral's own installer.
2. **Git**: if it is missing, `xcode-select --install` (Apple's command-line tools) or `brew install git`.
3. **Docker Desktop**: if it is missing and you have [Homebrew](https://brew.sh/), it offers
   `brew install --cask docker`; without Homebrew, it gives Docker's download page. Then it offers to open Docker
   Desktop and waits for it (up to five minutes): the first time, accept its terms in its window.
4. **Clank**: its latest release, with `uv tool install`, then `uv tool update-shell`.
5. **The check**: `clank doctor` (step 3).

</details>

<details>
<summary><b>Linux</b></summary>

1. **uv**: the one you have, or Astral's own installer.
2. **Git**: if it is missing, your package manager's command for it (apt, dnf, pacman or zypper), run with `sudo`.
3. **Docker Engine**, from Docker's own packages:
   - If it is missing, the installer reads your distribution (`/etc/os-release`), prints the exact commands Docker's
     [installation pages](https://docs.docker.com/engine/install/) give for it (adding Docker's package repository
     and its key, then installing `docker-ce` and its plugins; on Arch, Arch's own `docker` package), and asks once
     before running them with `sudo`. `sudo` asks for your password itself; the installer never sees it.
   - Then, if Docker is not running or would not start at boot, it offers `sudo systemctl enable --now docker`.
   - Then it offers to add your account to the `docker` group (`sudo usermod -aG docker $USER`), so you can use
     Docker without `sudo`. Docker says plainly what that means: the group gives root's rights on that computer
     ([Docker's note](https://docs.docker.com/engine/install/linux-postinstall/)). Clank needs it to run the agent's
     containers as you.
   - Docker from the snap, or rootless Docker, is not supported (they cannot reach the folders Clank needs, or they
     map the agent's user to another one); the installer says so, and can install Docker Engine beside it.
4. **Clank**: its latest release, with `uv tool install`, then `uv tool update-shell`.
5. **The check**: `clank doctor` (step 3).

</details>

### Settings

Set these before the installer, as `CLANK_YES=1 sh` on macOS and Linux, or `$env:CLANK_YES = '1'` first in
PowerShell:

| Setting | What it does |
| --- | --- |
| `CLANK_VERSION=main` | installs Clank's main branch (or any tag) instead of the latest release |
| `CLANK_YES=1` | answers yes to every question, for a script; the commands are still shown |
| `CLANK_DRY_RUN=1` | macOS and Linux: shows every command that would change the computer, and runs none |
| `CLANK_NO_MODIFY_PATH=1` | changes no path: neither uv's installer nor `uv tool update-shell` touch it |

### Or by hand, from a clone

For working on Clank itself, or for building Clank's VS Code extension yourself (step 2b).

<details>
<summary><b>Windows</b></summary>

```
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id Docker.DockerDesktop -e
```

Open Docker Desktop once, accept its terms and let it finish starting. Open a new PowerShell, then:

```
git clone https://github.com/clank-ai/clank
cd clank
uv tool install --editable .
uv tool update-shell
```

</details>

<details>
<summary><b>macOS and Linux</b></summary>

Install Git with your system's package manager, uv with `curl -LsSf https://astral.sh/uv/install.sh | sh`, and Docker
as step 2 above says (or run the installer once for Docker alone). Open a new terminal, then:

```
git clone https://github.com/clank-ai/clank
cd clank
uv tool install --editable .
uv tool update-shell
```

</details>

## 2b. Build the VS Code extension (optional)

Clank's VS Code window (`c` on **This folder**, or `clank code`) shows the agent beside your files, its changes for
you to review and figures to mark up. It needs Clank's extension, built once from a clone (step 2, the second way)
and again after an update that changes it; until then, `c` says the extension is not built. It needs VS Code and
Node.js 22 or newer.

<details>
<summary><b>Windows</b></summary>

```
winget install --id Microsoft.VisualStudioCode -e
winget install --id OpenJS.NodeJS.LTS -e
```

</details>

<details>
<summary><b>macOS and Linux</b></summary>

VS Code from [its download page](https://code.visualstudio.com/download) (on Linux, its `.deb` or `.rpm`, which also
puts `code` on your path), and Node.js 22 or newer from [nodejs.org](https://nodejs.org/) or your package manager.

</details>

Open a new terminal, then in the `clank` folder:

```
cd vscode
npm ci
npm run build
cd ..
uv run --no-dev python -m tools.vsix
```

The last command writes `vscode/clank-<version>.vsix` (the extension's own version, 0.10.4 now). Clank's VS Code window
installs it by itself; to have it in your usual VS Code too: `code --install-extension vscode/clank-0.10.4.vsix`.

## 3. After installing

1. **Open a new terminal**, so it finds `clank` (`uv tool update-shell` put it on the path of new ones).
2. **Docker**:
   - *Windows and macOS*: Docker Desktop runs (its whale is in the taskbar or the menu bar). After a restart it starts
     when you sign in, if you let it in its settings.
   - *Linux*: if the installer just added you to the `docker` group, **log out and in once** (or restart), so every
     program you start can use Docker. Until then Clank says "this account may not use Docker yet" and what to do.
3. **Check the computer**: `clank doctor`. It changes nothing. Each line is `ok`, `warn`, `fail` or `skip` (a check
   that does not apply here, such as WSL on Linux), with what to do under each that is not `ok`. On a computer without
   an NVIDIA GPU, "An NVIDIA GPU" warns, and that is fine for a cloud model.

## 4a. A cloud model, through OpenRouter

OpenRouter gives one key for many providers' models, including free ones. Clank sends a workspace's requests there only
after you agree once, and only for the workspaces you allow.

1. **An account and a key.** Sign in at [openrouter.ai](https://openrouter.ai/), open
   [Keys](https://openrouter.ai/keys), press **Create Key**, name it (Clank), and copy it: OpenRouter shows it once.
   For paid models, add credits under **Credits**; free models (their names end in `:free`) need none, with lower
   limits.
2. **Type `clank`.** With no model set up, the console opens on **Add a model** (later: F12, or `a` on **Providers and
   models**).
3. Press `c` for **Cloud**, then Enter on **OpenRouter**.
4. Read the **agreement**: what goes to OpenRouter (the prompts and the files the agent reads in a workspace you allow),
   what never goes (Notion, and MCP servers marked local: Space marks or unmarks one), and OpenRouter's data policy
   (`o`). Press `y` to agree; `n` writes nothing.
5. **Paste the key** into the hidden field and press Enter. Clank checks it with OpenRouter once and keeps it in its
   own secrets folder only (`~/.clank/secrets`, readable by you alone); the console shows its last four characters,
   never the rest.
6. **Pick a model** from the live list: `/` searches, `s` sorts, `f` shows only the free ones. Enter picks it.
7. **Check its settings** (filled in for you) and press Enter. Clank sends one short test request and shows the answer
   and what it cost.
8. **Ready.** Clank says whether Docker is running (`s` starts Docker Desktop); Enter takes you to **This folder**.

What it costs shows on the header, Home, Requests (F7), the Monitor and `clank cost`. Set a daily or monthly limit
(`L` anywhere, or `clank cost limit`); when it is reached, cloud requests pause until you raise it.

## 4b. A model on your own GPU

Clank runs local models with llama.cpp or KVMem (an engine that keeps a long context partly in system memory). This
path is not one step yet: the engine is built and the model file downloaded, then a **preset** (the model with its
settings) is loaded into the main slot. Start from **Add a model** → `l` **Local**: it lists the presets with what each
needs and walks you through each step, asking first. One setup worth building, with every setting and why, is written
up in [docs/models/](models/README.md).

<details>
<summary><b>Windows</b></summary>

Engines run in WSL 2 (Ubuntu): the NVIDIA driver on Windows is enough, WSL sees the GPU through it. Add WSL as a host
once: `clank host add ubuntu-22.04 --wsl Ubuntu-22.04`.

</details>

<details>
<summary><b>Linux</b></summary>

Engines run on the computer itself. Install NVIDIA's driver from your distribution first (`nvidia-smi` must list the
card); `clank doctor` says what it sees.

</details>

<details>
<summary><b>macOS</b></summary>

Not possible: Clank's engines need an NVIDIA GPU. Use a cloud model (4a).

</details>

## 5. Work in a folder

1. Open a terminal in the folder you want to work in and type `clank`. The console opens on **This folder** (F4).
2. It lists what working here needs: Docker, the folder's workspace, its software, a model, the gateway. `g` does
   every step that is not done. The first workspace builds Clank's sandbox image, which takes a few minutes.
3. With a cloud model, Clank asks once whether this folder's work may go to OpenRouter. Answer `y`, or keep the folder
   on your computer only. `u` changes it later.
4. `a` starts **OpenCode** (the agent) in this terminal; leave it with `/exit` and the console comes back. Or `c`
   opens the folder in VS Code with OpenCode beside your files (step 2b).
5. In **review** mode (the default) the agent asks before it changes a file: answer under **Waiting for you** (`y`,
   `n`, `v` shows the change) or in VS Code. `r` switches to **auto**, where it changes files without asking.

The agent works in a container that sees only this folder. Commands it runs there change files in the folder without
asking, in either mode: keep the folder under version control (SECURITY.md says what Clank guards and what not yet).

Then look around: the **Monitor** (F10) shows what the agent does and what fills its context window, and lets you
stop, pause, guide or undo it; **Flows** (F10's Flow view, `n`) split a larger piece of work into steps, each a fresh
session. [docs/console.md](console.md) explains every page and key.

### Let the agent reach the internet

A workspace's container reaches nothing but Clank by itself. When the agent needs a host (a package index, a
paper's site, a documentation site), allow that host for that workspace, and only it: `clank workspace allow
FOLDER --host pypi.org --host .arxiv.org` (a name, or a suffix starting with a dot for a site and everything under
it; `--no-host` takes one back), or a named set with one word: `--set papers` (arXiv, Semantic Scholar, Crossref,
OpenAlex, DOI), `--set python`, `--set code`, `--set data`, `--set docs` (`clank workspace sets` lists them; the file
`config/network-sets.json` in your Clank home is yours to change). The agent's requests go through Clank's proxy, which
lets them out to the hosts allowed; a host not allowed is asked for: the request waits up to a minute while the
question shows under **Waiting for you** (`y` allows it always for the workspace, `o` once, `n` refuses it, and it is
not asked again for ten minutes); refused, the agent reads why in plain words. Private addresses (your machine, your
network) are never reached. Every exchange is logged in `logs/network/` by host, status, bytes and time, never by
content. A workspace made before this gets the proxy when it is next stopped and opened.

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

## 5b. Work from another computer, over SSH

With a model on your GPU, every window the PC draws slows the model down. Working from a laptop instead, with VS Code
on the laptop connected to the PC, leaves the PC's screen out of it
([design 0018 §8](design/0018-clank-code.md#8-vs-code-on-another-computer)). Written for a Windows PC; a Linux one needs
only its SSH server and Clank's service running.

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

## 5c. Clank on your iPhone

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
one. The phone keeps only its token and the last summary, names and numbers.

## 6. Updating

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
everything in `~/.clank` stay as they are. Running the installer again does the same for a release.

Run it at the computer itself, not over SSH (started from an SSH session, the service runs where it cannot use
Docker's sign-in, on Windows and macOS). If the VS Code extension changed, build it again (step 2b). If Clank then says
a workspace's container uses an older sandbox image, reopen that workspace: **Workspaces** (F6), `x` to stop it, then
`o` to open it again.

## 7. Troubleshooting

`clank doctor` checks the computer, and every refusal in Clank says why and what to do. The usual ones:

| What you see | What to do |
| --- | --- |
| `clank` is not found | Open a new terminal after the installer (`uv tool update-shell` put it on the path of new ones) |
| "Docker is stopped" | Start Docker: Docker Desktop on Windows and macOS (or `clank docker start`); on Linux, `sudo systemctl start docker` |
| A workspace says its container uses an older sandbox image | Reopen it: F6, `x`, then `o` |
| F10 opens your terminal's menu instead of the Monitor | `clank console --page monitor` |
| The key is refused (401) | Make a new key at OpenRouter and add it again (`clank endpoint key openrouter`) |
| "No credits" (402) | Add credits at OpenRouter, or pick a free model |

<details>
<summary><b>Windows</b></summary>

| What you see | What to do |
| --- | --- |
| Docker Desktop asks for WSL, or will not start after installing | Restart Windows; if it still asks, run `wsl --install` in an administrator PowerShell, restart, then open Docker Desktop |
| The installer cannot find winget | Update **App Installer** from the Microsoft Store, or install Git and Docker Desktop from their sites, then run the installer again |
| Scripts are disabled in PowerShell | The one line runs with `iex`, which the execution policy does not stop; for a downloaded copy, `powershell -ExecutionPolicy Bypass -File install.ps1` |

</details>

<details>
<summary><b>macOS</b></summary>

| What you see | What to do |
| --- | --- |
| `brew` is not found | Install Docker Desktop from [Docker's page](https://www.docker.com/products/docker-desktop/), open it once, then run the installer again |
| Docker Desktop waits for permissions | Open it, accept its terms, and let it finish starting; then `clank doctor` |

</details>

<details>
<summary><b>Linux</b></summary>

| What you see | What to do |
| --- | --- |
| "permission denied" on `/var/run/docker.sock`, or Clank says this account may not use Docker | Join the group (`sudo usermod -aG docker $USER`) if you have not, then log out and in once, then `clank stop` and `clank` |
| Docker is installed from the snap | Clank does not support it: install Docker Engine from Docker's packages (step 2), which Clank then uses |
| Docker stops after a restart | `sudo systemctl enable docker` |
| The installer does not know your distribution | Install Docker Engine as [Docker's pages](https://docs.docker.com/engine/install/) say for it, then run the installer again |

</details>

## 8. Uninstalling

Stop Clank and remove it:

```
clank stop
uv tool uninstall clank
```

Remove its workspaces' containers first if you like (**Workspaces**, F6, `d` on each). Clank's own folder keeps your
settings, records and keys: delete it to remove those too (`%USERPROFILE%\.clank` on Windows, `~/.clank` on macOS and
Linux). If the installer installed uv and nothing else uses it,
[uv's guide](https://docs.astral.sh/uv/getting-started/installation/#uninstallation) says how to remove it.

What the installer installed for Docker stays, since other programs may use it. To remove it too:

<details>
<summary><b>Windows and macOS</b></summary>

Uninstall Docker Desktop as any app (Windows: Settings → Apps; macOS: Docker Desktop's Troubleshoot menu → Uninstall,
then move it to the Trash).

</details>

<details>
<summary><b>Linux</b></summary>

Leave the `docker` group (`sudo gpasswd -d $USER docker`), then remove Docker Engine as
[Docker's pages](https://docs.docker.com/engine/install/ubuntu/#uninstall-docker-engine) say for your distribution:
on Ubuntu and Debian, `sudo apt-get purge docker-ce docker-ce-cli containerd.io docker-buildx-plugin
docker-compose-plugin`, then `sudo rm -rf /var/lib/docker /var/lib/containerd`, and
`sudo rm /etc/apt/sources.list.d/docker.list /etc/apt/keyrings/docker.asc` for Docker's repository.

</details>
