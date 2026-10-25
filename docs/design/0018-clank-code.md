# Design 0018: Clank Code, Clank inside VS Code

Roadmap part 6 (VS Code), extending the extension of decision 0028 and designs 0006-0010. Started 2026-10-23 at the
owner's request: "a complete integration of Clank into VS code ... make VS code dramatically easier to use with a local
LLM and ... a harness for opencode running the LLM". Its layouts are drawn in the owner's design canvas "Clank in VS
Code". Every section is proposed. Its first part to be built is the animation workbench,
[design 0019](0019-animation-workbench.md), at the owner's request.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | An extension, not a fork | Proposed 2026-10-23; the direction approved by the owner the same day ("A clank code extension sounds good") |
| 2 | The owner's answers | Recorded 2026-10-23 |
| 3 | The layouts | Proposed 2026-10-23 |
| 4 | Trust: what a claim's marks mean | Proposed 2026-10-23, from the critic's review |
| 5 | What the extension API allows, and what it does not | Proposed 2026-10-23 |
| 6 | Order of work | Proposed 2026-10-23 |
| 7 | Showing files to the owner | Approved 2026-10-25 (the owner: "Yes"); revised after approval 2026-10-25: §7.5, the agent's tools are always this Clank's (a running container kept an image without `show_files`, and the model told the owner to open the figure themselves) |
| 8 | VS Code on another computer | Proposed 2026-10-25 |

## 1. An extension, not a fork

Clank Code is Clank's VS Code extension grown to cover the whole window, in stock VS Code, plus later an optional
VSCodium-based build with the extension built in, its layout set, telemetry off and proposed APIs on (no patches to VS
Code's code). A full fork is rejected for now:

- Forks lose Microsoft's Remote-SSH, WSL, Dev Containers, Pylance and C/C++ extensions, which are licensed for VS Code
  only; the owner's next tests run over SSH and in WSL.
- Keeping a patched copy in step with VS Code's monthly releases takes a funded team; Void, the open-source Cursor
  alternative, was archived in June 2026.
- Almost everything Clank needs is reachable from an extension, including its models in VS Code's own Chat and agent
  mode through the Language Model Chat Provider API (stable since VS Code 1.104).

Triggers to reconsider: a part of the window Clank must own that no API reaches; an API Clank depends on removed or
blocked; enough maintainers to merge upstream monthly.

## 2. The owner's answers

- Research to support first: LaTeX papers, experiments and jobs, literature. (Lean 4 later.)
- The agent: both Clank's own panel (OpenCode) and VS Code's Chat with Clank's models.
- Productivity: review per change and rewind, fast-model editing, hooks and specs; parallel sessions dropped ("Drop the
  parallel sessions if we need to"): one session at a time, earlier ones resumable.
- Figures: a simple annotation loop for figures the model makes (matplotlib, pgfplots and TikZ), "making sure that
  the user experience is prioritized alongside the usability and reliability of the implementation"; and Manim
  animations made together, the first part to design fully and build (design 0019).
- While the model works: the status bar only; the Monitor on demand.
- LaTeX builds on the LaTeX Workshop extension (its build, PDF viewer and SyncTeX).
- Literature tools may search outside the folder automatically (arXiv, Semantic Scholar, zbMATH): queries leave the
  computer, files and code never do.
- Long experiments run on this computer and on the HPC (Slurm over SSH), tracked in one list.

## 3. The layouts

Drawn in the canvas: the working layout (Clank's side bar with the session, flows, jobs, memory and the model; the
editor with per-change review; the agent panel; the Monitor opened from the status bar; a status bar with the model,
its speed, the context used, the mode and questions waiting), the research layout (a library of the folder's papers,
a PDF beside the LaTeX source, the claim states and the verification ladder in the agent panel, jobs including the
HPC's), the figure loop and the animation workbench (design 0019).

## 4. Trust: what a claim's marks mean

From the critic's review (a fresh agent, 2026-10-23, 5 of 10 for research): a check mark must never mean more than
was checked. Each claim the model makes shows three states: **source found** (the cited place exists), **conditions
match** (the source's assumptions cover this use) and **inference checked** (by a computation, Lean, or the owner);
only the last is shown as checked. Novelty is never "new": it is "not found in N sources (listed) as of a date", and
an unread candidate keeps it open. Each rung of the verification ladder names its claim, its evidence (file, commit,
seed, command, log) and who checked it; a review by the same model in a fresh session says so. Text the model writes
into a paper before its claim is checked is marked `% UNVERIFIED`. Memory entries link to the run or message they came
from and can be retracted.

## 5. What the extension API allows, and what it does not

An extension cannot place its views in the secondary side bar itself (the owner drags the agent panel there once, or
the Clank Code build sets it); the accept and reject actions on a change are CodeLens lines or comment threads, not
buttons drawn between lines; next-edit completion and the Agent Sessions view use proposed APIs, which Marketplace
extensions may not use (so they wait for the Clank Code build or the API's release). Videos play in a webview as
WebM, since VS Code's webviews may lack H.264.

## 6. Order of work

1. The animation workbench (design 0019): the owner's first test.
2. The figure loop for matplotlib, pgfplots and TikZ (design 0008 extended).
3. The agent panel, per-change review with rewind, the status bar and the Monitor on demand.
4. Research: the library with citation states and outside search, LaTeX with LaTeX Workshop, the job list with the HPC.
5. Clank's models in VS Code's Chat; hooks and specs; fast-model inline edit.
6. The Clank Code build, when a proposed API is worth it.

## 7. Showing files to the owner

In Clank's VS Code window (opened from the Clank menu, design 0004 §5), OpenCode runs in a terminal on the right and
the files on the left. The owner asks the agent to find a figure or a file and put it in front of them: "if I ask the
model to go ahead and pull up a figure then I want to be the one to visually inspect it and in that case there is no
reason for the model to inspect it."

### 7.1 The agent opens files

The agent's tool `show_files(paths, why)` (Clank's MCP server in the container) opens files of the folder in the
window: figures, PDFs, LaTeX, code, notes, any file, up to 12 at once, named from the folder or under `/workspace`. It
asks the gateway (`POST /agents/show`, the only route under `/agents/` the agent may ask), which forwards it to the
service as the client `agent`. The service checks that each path is a file of the workspace's folder (none outside it,
none missing: the answer names each), then records the event `agents.shown` (the workspace, its folder, the files,
the why). Its answer tells the model what was opened, and that the owner looks at it themselves. With no VS Code
window following the service, nothing is opened and the answer says so, so the model gives the owner the paths
instead.

The tool's description is an order: when the owner asks to see, open, show or pull up something, find it, call
`show_files`, say in a line what was opened, and stop; do not read, describe or check what was opened (no
`look_at_figure`) unless the owner asks for that too.

### 7.2 The window opens them on the left

Clank's extension follows the events; on `agents.shown` for a folder open in its window, it opens each file in the
files' group (never the agent's), without taking the keyboard from OpenCode, each in its own tab (not a preview tab
the next replaces), as VS Code opens that kind of file: a PNG or JPEG in Clank's figure annotator (design 0008 §6), so
the owner can mark it up and send it back as from any figure they open themselves; a PDF in the PDF viewer the window
has; text in the editor. The why shows once as a line in the window. A file that does not open is said, the rest open.

### 7.3 Paths in the agent's terminal are links

OpenCode prints paths as the container sees them (`/workspace/plots/residual.png`), which VS Code cannot open on the
machine. The extension makes each such path in the agent's terminal a link to the folder's file; a click opens it on
the left, as §7.2 does.

### 7.4 Finding figures

`find_figures(query)`: the figures of the folder best matching words, from what Clank knows of each: its
name and folder, the title, axis labels and legend Matplotlib recorded when it was saved (design 0008 §3), the script
that made it, a LaTeX `\caption` it is under, and when it was made; the best few, each with why it matched, for
`show_files`.

### 7.5 The agent's tools are this Clank's

Clank's MCP server (`show_files` and the rest) and its instructions to the agent were in the sandbox image, so a
workspace's container kept the ones of the image it was made from until it was made again: on 2026-10-25 the owner
asked the model to open a figure and it answered that it could not, there being no `code` command in its container.
Each time Clank starts an agent there (`prepare`, and `configure` for one without a terminal, a flow's), it now writes
its current MCP server (`phone_mcp.py`, with `find_figures.py`) and its instructions into the agent's home
(`/home/agent/.clank/`), and the agent's configuration runs and reads those: the agent's tools follow Clank's version,
whatever image its container runs. The instructions say how a file is opened for the owner (`show_files`), since the
model looks for a `code` command otherwise.

## 8. VS Code on another computer

Started 2026-10-25 at the owner's request: when they work on the PC from another computer over SSH, the Clank menu's
VS Code should open on that computer, connected to the PC, "so that we can dramatically reduce the number of other
things that my PC is having to do/display so that we can dramatically increase the number of tokens per second" (a
window redrawing on the PC was measured to halve the model's decoding speed). Microsoft's Remote-SSH extension on the
other computer does the connecting; Clank only decides where its window opens and sets the PC's side up.

### 8.1 Where the window opens

The client that asks (the console's `c`, `clank code`, a planning's `N`) knows where the owner sits (design 0013 §15,
decision 0099), and opens VS Code there:

- **At the PC** (no SSH): Clank's own VS Code window on the PC, as before (design 0004 §5).
- **In a VS Code Remote-SSH terminal** (the other computer's VS Code connected to the PC, its terminal on the PC): the
  terminal has VS Code's remote command (`code` on the path under VS Code's server, its `remote-cli` folder, with
  `VSCODE_IPC_HOOK_CLI` set), which talks back to the window it belongs to. Clank uses it to open the folder in a new
  window of that VS Code, on the other computer, connected to the PC (§8.2).
- **In any other SSH terminal**: nothing can open on the other computer from it, and nothing opens on the PC's screen,
  which no one sees. Clank prints the command to run on the other computer, `code --folder-uri
  "vscode-remote://ssh-remote+HOST/c:/path/to/folder"`, HOST being the setting `ssh_host` of Clank's VS Code settings
  (`config/vscode.json`: the name the other computer's SSH configuration gives the PC), else the address the SSH session
  came in on.

### 8.2 Setting the PC's side up

Before the folder opens, Clank sets up VS Code's server on the PC (`~/.vscode-server`, the one Remote-SSH started),
each step only when needed and said as it goes:

- **Clank's extension and the window's others** are installed there, through the remote command (`code
  --install-extension`, which installs on the PC's side): Clank's own when that version is not installed, and each
  extension of the settings' list that is missing, as for Clank's window on the PC.
- **Clank's settings** are added to the server's machine settings (`~/.vscode-server/data/Machine/settings.json`),
  each only when missing: the agent opened beside the files, figures in the annotator, word wrap, LaTeX Workshop's
  recipe. VS Code ignores there the settings that belong to the other computer (its telemetry, its title bar), which
  stay the owner's own.

Clank's extension then runs on the PC's side (it is installed only there, and may run on either side), so it reaches
the Clank service as on the PC: OpenCode opens in a terminal on the right, running on the PC, and files, figures,
reviews and the annotator open on the left, drawn by the other computer. The other computer needs VS Code and
Remote-SSH, and an SSH key to the PC; nothing of Clank. If Clank's extension were also installed in the other
computer's own VS Code, it would run there instead and find no service: VS Code's setting `remote.extensionKind` with
`{"clank.clank": ["workspace"]}` keeps it on the PC's side.

### 8.3 What the PC no longer does

The PC draws no window for the work: VS Code's server and OpenCode's terminal run there without a screen. Locking the PC
or turning its screens off takes the rest of its drawing away.
