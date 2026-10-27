# Design 0028: Setting Clank up, plug and play

From nothing to an agent answering in a folder, by following what Clank says, on Windows, macOS and Linux, with a
model in the cloud, a model on the computer's own GPU, or both. The owner asked for it on 2026-10-27: "make sure that
the clank setup is basically just a plug and play: first checks if we have all the required dependencies like Docker,
then if we don't it gives us the option to go ahead and download these dependencies as well as immediately configure
them correctly and set everything up. The setup for Clank needs to be designed extremely well and in a way that makes
it EXTREMELY easy for someone to set up on their own without using an LLM to set everything up for them". The same day
the owner began testing Clank on a separate Linux computer with OpenRouter only, so the build steps put that path first
(§8).

It builds on what is there: the one-line installers (getting-started §2), `clank doctor` (design 0002 §2.15), the
console's Add a model and This folder (design 0016 §14, design 0004), `clank update` (design 0026), and Docker Engine on
Linux ([design 0014](0014-linux-and-small-machines.md) §2-§4, built at the owner's instruction the same day).

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | Who sets Clank up, and the one path each follows | Proposed 2026-10-27; being built at the owner's instruction |
| 2 | Rules every step of the setup keeps | Proposed 2026-10-27; being built at the owner's instruction |
| 3 | The installer on each system | Proposed 2026-10-27; built 2026-10-27 on the website (`install.sh` c9727ce, `install.ps1` 05f8fa9) |
| 4 | `clank setup`: the checklist, and the fixes it can make | Proposed 2026-10-27; being built at the owner's instruction |
| 5 | Docker, configured correctly on each system | Proposed 2026-10-27; being built at the owner's instruction |
| 6 | Clank's VS Code extension without building it | Proposed 2026-10-27; built 2026-10-27 at the owner's instruction (S5) |
| 7 | Local models: what is one step and what is not yet | Proposed 2026-10-27 |
| 8 | Tests and build steps | Proposed 2026-10-27; the installers' tests built (the website's `installer` workflow) |

## 1. Who sets Clank up, and the one path each follows

Three people, one path:

| Who | Models | What they need |
| --- | --- | --- |
| No GPU, or not one worth using | In the cloud, through OpenRouter | An OpenRouter key; Docker for the agent's workspaces |
| A GPU, and models kept on the computer | On the GPU (llama.cpp or KVMem) | The engine and a model file; Docker |
| Both | Local by default, a frontier model in the cloud when it helps | Both of the above |

The path is the same for all three, and the same on every system:

1. **Install**, with one line (§3). It checks what Clank needs, offers to install what is missing, and configures it.
2. **`clank`**. While anything is missing, the console opens on **Setup** (§4): a checklist that says what is done,
   what is not, and does the next step on one key.
3. **A model**: cloud, local or both. The cloud is three answers and a pasted key; local lists the presets that fit
   the GPU found, with what each needs.
4. **A folder**: This folder, where `g` does every step that is not done.
5. **The agent**, in the terminal or in Clank's VS Code window.

Done means the checklist says **Ready**: Docker runs and Clank can use it, the sandbox image is built, a model has
answered a test request, and the folder has a workspace whose agent starts. The setup is good when someone new reaches
Ready without reading anything but what Clank shows, and with only two things done in a browser: getting an OpenRouter
key, and accepting Docker Desktop's terms on Windows and macOS.

## 2. Rules every step of the setup keeps

- **It says what it does and why**, before it does it, in plain words: "Docker runs the agent in a container of its
  own for each folder, so it sees only that folder."
- **It asks before it installs anything, or runs anything with administrator rights**, and shows the exact commands
  first. One yes covers the commands shown, and nothing else. `--yes` (or `CLANK_YES=1` for the installer) answers yes
  for scripts; it never extends to anything not shown.
- **It never asks for or stores a key** outside Clank's own Add a model, which keeps it in Clank's secrets folder
  (SECURITY.md).
- **It changes nothing silently, and can be run again.** Run again, the installer updates Clank and repairs what is
  missing; `clank setup` says what is done and offers only what is not.
- **It installs from each project's own source**: uv from Astral, Docker from Docker's own packages or installer,
  Clank from its GitHub releases, each over HTTPS. It installs nothing from a mirror or a third party's script.
- **A step that fails says why, in the program's own words, and what to do**, and the setup goes on with what does not
  depend on it.
- **It can be undone.** Getting started's Uninstalling section says how to remove what the setup installed, and the
  setup names what it installed when it is done.
- **It works without an LLM.** Nothing in the setup asks the person to ask a model what to do: every refusal and
  every fix is written out where it is shown.

## 3. The installer on each system

The installers stay short, readable scripts on the website (`install.ps1`, `install.sh`), in five numbered steps. What
changes is step 3, Docker, which today only says where to get it on macOS and Linux, and a last step that hands over
to `clank setup`.

- **Windows** (`install.ps1`). uv, Git and Docker Desktop with winget, asking first, as now. Then, while Docker
  Desktop is new: it opens Docker Desktop once and waits for its engine (up to five minutes, saying so), because its
  terms must be accepted in its own window. WSL 2: Docker Desktop turns it on; when `wsl --status` says it is off, the
  installer says that a restart may be needed and that Docker Desktop will ask.
- **macOS** (`install.sh`). Git through `xcode-select --install`, as now. Docker Desktop: with Homebrew,
  `brew install --cask docker`, asking first; without it, Docker's download page. Then it opens Docker Desktop once
  and waits for its engine, as on Windows.
- **Linux** (`install.sh`). Docker Engine is installed from Docker's own packages, never the snap's (design 0014 §2):
  - The distribution is read from `/etc/os-release` (`ID`, `ID_LIKE`, `VERSION_CODENAME`). Ubuntu, Debian and their
    derivatives get Docker's apt repository; Fedora, RHEL, CentOS Stream and Rocky get Docker's dnf repository; Arch
    gets Arch's own `docker` package, with the full upgrade Arch asks for (`pacman -Syu`). Each is the list of commands Docker's installation pages give
    (https://docs.docker.com/engine/install/). Another distribution is told where those pages are, and the installer
    goes on.
  - Docker from the snap, or rootless Docker, found already: the installer says Clank does not support it and why
    (design 0014 §2), and how to install Docker Engine beside it.
  - Configured: `sudo systemctl enable --now docker` (started now, and at each boot), and the account added to the
    `docker` group with `sudo usermod -aG docker $USER`. Before the second, it says what Docker itself says: the group
    gives root's rights on that computer (https://docs.docker.com/engine/install/linux-postinstall/). The group takes
    effect at the next login: the installer runs its own last checks through `sg docker`, and says to log out and in
    once before `clank`. `clank setup` notices when that is not done yet (§5).
  - Checked: `docker version` answers for the account, through the group.
- **The last step** runs `clank setup --check` (§4) where it ran `clank doctor`: the checklist, with what to do next.
  A Clank without `clank setup` (0.3.0b2 and older) gets `clank doctor`, as before.
- **What building it found** (2026-10-27): Docker's packages start the service and enable it at boot by themselves on
  Ubuntu, so that question is asked only where they do not; Fedora 41's dnf5 adds a repository with `addrepo
  --from-repofile=`, older dnf with `--add-repo`; a fresh Arch has no package database until `pacman -Sy`, and Arch
  forbids partial upgrades, hence `-Syu`. The Docker step ran for real, as root, in Ubuntu 24.04 and 22.04, Debian 12,
  Fedora 41, Rocky 9 and Arch; and the whole installer on GitHub's Ubuntu 24.04 runner with its Docker removed first,
  after which Docker ran, started at boot, and the account ran a container through the docker group.
- **`CLANK_YES=1`** answers yes to every question, for a script; **`CLANK_DRY_RUN=1`** prints every command the
  installer would run and runs none, which the tests use (§8).

## 4. `clank setup`: the checklist, and the fixes it can make

`clank setup` is the console's **Setup** page, also run as a command. The console opens on it while any of its items
is not done; afterwards it is in the menu.

| Item | Done when | The fix it offers |
| --- | --- | --- |
| Docker installed | the platform's adapter finds it | the installer's Docker step, run in the terminal |
| Docker running | the adapter says running | start it (Docker Desktop), or `sudo systemctl start docker` in the terminal (Linux) |
| Docker usable by this account | not *no access* | the docker group, then log out and in (Linux; §5) |
| The sandbox image | built for this Clank | build it now, in the background (a few minutes, once) |
| Clank's service | it answers | start it |
| A model | a preset answered a test request | Add a model: cloud, local or both (§1) |
| A folder | a workspace exists | This folder, for the folder `clank` was started in |
| Clank's VS Code window | optional: its extension installed | install it (§6) |

- **As a command**, `clank setup --check` prints the checklist and changes nothing; `clank setup` asks about each
  item that is not done, in order, and does it on a yes; `--yes` does every fix that needs no administrator rights,
  and says the others.
- **Fixes that need administrator rights** run in the terminal, where `sudo` (or Windows' prompt) asks for the
  password itself. Clank never asks for it, never keeps it, and runs nothing as root on its own.
- **The model step** asks once: "Run models in the cloud through OpenRouter, on this computer's GPU, or both?" The
  GPU found is said first ("NVIDIA GeForce RTX 5080, 16 GB": local models fit), or that there is none ("no GPU Clank
  can use: the cloud is the way"). Cloud is Add a model's cloud path as it is; local is its local path; both is cloud
  first, then local.
- **Ready** says what was set up and what each thing is for, then opens This folder.

## 5. Docker, configured correctly on each system

Each state the platform reads (design 0014 §2) has its words, its fix, and whether Clank can do the fix itself:

| State | What Clank says | The fix | Clank does it |
| --- | --- | --- | --- |
| Not installed | the agent runs in Docker; how to install it | the installer's Docker step | in the terminal, on a yes |
| Snap or rootless Docker | not supported, and why | Docker Engine from Docker's packages | no: the commands are shown |
| Stopped (Linux) | Docker Engine is stopped | `sudo systemctl start docker` | in the terminal, on a yes |
| Stopped (Windows, macOS) | Docker Desktop is not running | start it | yes |
| Not started at boot (Linux) | it will be stopped after a restart | `sudo systemctl enable docker` | in the terminal, on a yes |
| No access, not in the group | this account may not use Docker | `sudo usermod -aG docker $USER`, then log out and in | in the terminal, on a yes; the login is the person's |
| No access, in the group | the group is not active in this session yet | log out and in, then `clank stop` and `clank` | no |
| No memory limits | Docker cannot limit a container's memory | the kernel setting (design 0014 §4) | no |
| A folder the agent cannot write | the agent's account cannot write it | the folder's permissions, or another folder (design 0014 §4) | no |

## 6. Clank's VS Code extension without building it

Today Clank's VS Code window installs the extension built from Clank's folder (`tools.vsix`, with Node), so a release
installed by the one-line installer has none. Each release carries it instead:

- When a version tag is pushed, CI builds the extension, attaches `clank-<version>.vsix` to the GitHub release with
  its SHA-256, and marks a beta a pre-release.
- `clank code`, in a release install, downloads the extension of the release that matches Clank's own version, checks
  its SHA-256 against the release's, and installs it. A clone builds its own, as now.
- No Node and no build are needed to use Clank's VS Code window.

As built (2026-10-27): CI's job `release` (`.github/workflows/checks.yml`) runs once every check passed on a tag `v*`,
builds the extension as a working copy does (`tools.extension`, `tools.vsix`), and makes the release with
`tools/release.py`: the tag must be Clank's own version, the release carries `clank-<the extension's version>.vsix` and
`SHA256SUMS`, a tag with a, b or rc is a pre-release, and its notes are the version's section of CHANGELOG.md (or a
link to it). A release install is one whose folder has no extension's sources; `clank code` there reads the release
`v<Clank's version>` from GitHub's API, refuses a file whose SHA-256 is not the one SHA256SUMS gives, keeps the
extension under CLANK_HOME/vscode/cache/<tag>/ and uses that copy afterwards without asking GitHub
(`clank/components/agents/extension.py`). No release, a release without the extension or its sums, or no answer from
GitHub is said with what to do, and the folder opens all the same.

## 7. Local models: what is one step and what is not yet

- **llama.cpp** is installed by Clank's recipe (design 0003 §7.1), with the model file from Clank's catalog, checked
  against its SHA-256. That path is one step from Add a model's local path.
- **KVMem**, which frontier 262K needs, is built by hand ([docs/models/frontier-262k.md](../models/frontier-262k.md)).
  The setup says so, and offers llama.cpp's presets meanwhile. A recipe for KVMem is a later design: it would pin
  KVMem's source, Clank's patch (decision 0146) and the build's settings, and build in its own environment (decision
  0032).

## 8. Tests and build steps

Tests:

- **The installers.** `shellcheck` on `install.sh`. Run with `CLANK_DRY_RUN=1` in a container of each distribution
  (Ubuntu 24.04, Debian 12, Fedora, Arch), the commands printed for Docker are the expected list. A hand-run CI job on
  GitHub's Ubuntu runner removes Docker, runs the installer with `CLANK_YES=1`, and checks that Docker runs and the
  account may use it.
- **`clank setup`.** For each Docker state of §5 and each answer of §4, headless, with recorded platforms: the
  checklist's words, the fix offered, and that nothing runs without its yes.
- **End to end on Linux.** In CI on Ubuntu with Docker Engine: the service, a workspace, the agent's container
  reaching the gateway through the edge (design 0014 §3), and a stand-in OpenRouter: the agent's request reaches the
  stand-in and its answer comes back.

Build steps, the owner's Linux test with OpenRouter first:

| Step | What | After |
| --- | --- | --- |
| S1 | The Linux installer installs and configures Docker Engine (§3), with its dry run and its tests | design 0014's L2 (the adapter) for the words |
| S2 | `clank setup --check` and the console's Setup page, first while anything is missing (§4) | design 0014's lane L |
| S3 | The fixes of §5 that run in the terminal, each on a yes | S2 |
| S4 | The sandbox image built during the setup (§4) | S2 |
| S5 | The extension attached to each release, and installed from it (§6) | nothing |
| S6 | macOS's Docker Desktop through Homebrew, and Windows' wait for Docker Desktop's first start (§3) | S1 |
| S7 | The end-to-end test on Linux (§8) | design 0014's lane L |
| S8 | Getting started written around `clank setup` | S1-S4 |
