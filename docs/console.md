# The console: where each thing is, and how to change it

The console (`clank`, `clank console`) is a Textual app that is a client of the service: it holds nothing of its own
(design 0001 §5). This page says where each part of the screen comes from and what to edit to change it (design 0004
§9: easy to use, dynamic, and easy to change).

## Setting Clank up

While anything Clank needs is missing, `clank` opens the console on **Setup** (the menu's last page; Ctrl+P finds it;
a Docker Desktop not started yet and a sandbox image an update made stale are This folder's to do, so they open This
folder):
Docker installed, running and usable by your account, Clank's service, the sandbox image, a model that answered a test
request, a folder that is a workspace, and Clank's VS Code window, which is offered. Each item says what it is now
and, while it is not done, what to do with the key that does it here: `s` starts Docker Desktop, `t` runs a command
that needs administrator rights (on Linux, `sudo systemctl start docker`, or joining the `docker` group) in this
terminal, asked first (the console steps aside, sudo asks for your password itself, and the console comes back), `b`
builds the sandbox image in the background (asked first; its item says how far it is), `m` opens **Add a model** (in
the cloud through OpenRouter, on this computer's GPU, or both), `f` opens **This folder**; `r` reads it all again. Once everything is
done it says what was set up and what each thing is for, and `f` opens This folder. `clank setup --check` prints the
same checklist in a terminal, without the service if need be, and `clank setup` offers each fix there, one by one
(design 0028 §4).

## Working in a folder, quickly

1. Open a terminal in the folder you want to work in and type `clank`. The console opens on **This folder** (F4).
2. The list says what working there needs (Docker, the folder's workspace, its software, a model, the gateway): a ✓
   for each step done, a ✗ and the key that does it for each that is not. `g` does every step that is not done; a
   spinner turns on the step being worked on, and "What runs from here" says how far it is.
3. **Its software** (`e`): the folder's own packages, installed into the workspace so the agent can run its tests,
   scripts and MCP server. Clank proposes the command from `pyproject.toml` or `requirements.txt`; `e` shows it in a
   form to change or take as it is. It downloads in a container of its own; the agent's reaches the internet only
   through Clank's proxy, host by host as you allow (below).
4. **MCP servers** (`m`): listed under "Then work". Yours (F3) are given to the agent; a folder's own (its
   `.mcp.json`) only once you allow it. `m` gives one or takes it away, and checks one given in the workspace's
   container: its tools show beside it. The **MCP servers** page (F3) shows them all with their state (running,
   stopped or failed while an agent runs; on or off while none does) and their tools: Enter lists a server's tools
   with their parameters, `s` starts or stops it (at once in a running agent, and for its next start), `c` checks it.
5. **Hosts** (`h`): the internet hosts the workspace's agent may reach through Clank's proxy, listed under "Then
   work" (design 0024). `h` allows a named set (papers, python, code, data, docs: each says what it opens) or a
   host by name, or takes one back; a host the agent reaches without an allowance holds its request while a
   question waits for you (`y` always, `o` once, `n` no), except in dev mode (`D` on Providers and models), where
   every public host goes out at once and private addresses still never (decision 0152). **Requests** (F7) shows
   every exchange with `n` (why each went out or was refused, `dev mode` among them), and `clank network log` and
   `clank network hosts` the same from the command line.
6. Then `a` starts OpenCode in this terminal (leave it with `/exit`: the console comes back), or `c`
   opens the folder in Clank's VS Code window: your files on the left, OpenCode in a terminal at the right edge (kept
   there: a window that had it elsewhere moves it back, and a reloaded window never starts a second one).
7. **The agent's changes** (`r`): in **review** (the default) the agent asks before it changes a file. In VS Code the
   change opens beside your files (the file as it is, and as the agent would leave it), with **✓ Accept** and
   **✗ Reject** in the tab's title bar; a reject asks what to tell the agent. It can also be answered in the agent's
   terminal, under "Waiting for you" here (`y`, `n`, `v` shows the diff), or from the phone. In **auto** the agent
   changes files without asking, and VS Code shows each change after it is made. `r` switches; so does the **Review**
   / **Auto** item in VS Code's status bar.
8. **CPU models** (F8): the small models on the CPU. Completion: gray text after the cursor in VS Code; `l` gets it
   served (it installs llama.cpp's CPU build and downloads the model, about 506 MB, the first time), `u` stops it, `x`
   turns it off or on in VS Code; the page shows how fast the last completions were answered. Vision: the model that
   reads images (for a figure you marked up, when the agent's model cannot see it, and for the agent's
   `look_at_figure`); `v` switches it off, on demand (the default: loaded when needed, unloaded after 10 idle minutes)
   or always; `g` downloads its files (about 2.7 GB).
9. **Figures**: in Clank's VS Code window a PNG or JPEG opens in the annotator: draw on it (pen, box, circle, arrow,
   note), say what to do, Enter sends it to the agent, with each mark said in the figure's own terms.
9. Home (1) says what happens now; the panel on the right shows the machine; the menu's badges say what needs you
   (questions waiting, a model that stopped, an operation running).

`clank work` and `clank code` do it from the command line, without the console; `clank workspace setup` installs the
folder's software, and `clank mcp allow NAME` gives a server to the folder's agent. Running simulations and studies
with the agent: [studies.md](studies.md); the whole workflow, step by step: [walkthrough.md](walkthrough.md).

## Building a flow with the model, then letting it run

A flow is the work as a program of boxes, each a fresh session of the model (design 0013). To build one by talking it
through (§15):

1. Once everything in **This folder** is ready, press `f` there, or `n` on the Monitor's **Flow view** (F10, again
   until its Flow tab is on; or start the console on it, `clank console --page monitor --view flow`).
2. A planning opens: a new session of OpenCode's whose first message tells the model how to build a flow (kept as
   `first-message.md` beside the planning, in Clank's state). The console keeps its terminal and shows the Flow view;
   OpenCode opens beside it: in Windows Terminal, in a pane split off on the right; in VS Code's terminal (or with `N`),
   in Clank's VS Code window; elsewhere, and always over SSH, nothing opens and the view says what to type in another
   terminal: `cd <the folder>` then `clank flow attach`.
3. Talk with the model there. It reads the folder, asks you what it needs, writes `BRIEF.md` with you, then drafts the
   flow; Clank checks each draft and tells the model what to fix, then writes the flow. Meanwhile the Flow view shows
   it built: **Building it with the model** (in Selected's place) lists its steps, reading the folder (its tool calls
   so far), waiting for your answer, `BRIEF.md` written, each draft refused with its problems whole, or accepted, and a
   **Live** box for the session; the latest draft is drawn in the Flow panel, marked DRAFT, even when refused. Enter
   opens the planning session in the Session view, Esc comes back.
4. Once a draft is accepted, the view shows the built flow: its boxes and their models, and in **Waiting for you** the
   check's warnings. `e` changes a box first.
5. `r` runs it. A built flow asks nothing on the way: the tasks its DECOMPOSE proposes join on their own, a VERIFY
   sends work back on its own up to its tries, and it waits for you only at its last box, your review, or when a box
   runs out of tries. The question "flow built: look, then r to run" shows on the console, the phone and VS Code too;
   its *Run it now* starts it from any of them.

`clank flow new [NAME]` opens a planning from the command line, OpenCode in that terminal (`--vscode` for VS Code).
`clank flow attach [--workspace W]` opens OpenCode in this terminal on the planning open in the folder's workspace (its
session started there, shown when it already talks, tried again when it failed), and comes back when you leave
OpenCode; with none open it says so. One OpenCode window per workspace: another window open there is closed first,
and it says so.

**Over SSH** (a terminal on another computer, `ssh` into this one; on Windows, OpenSSH's server and its `cmd.exe`):
nothing ever opens on this computer's screen (Clank sees `SSH_CONNECTION`). Open two SSH windows side by side, both
in the folder:

```
clank console --no-start --page monitor --view flow   # the left window: the Flow view at once; n builds, r runs
clank flow attach                                     # the right window, once n was pressed: talk with the model
clank flow run <name>                                 # or run it from the command line
```

`clank flow new` builds it in one SSH window instead, without the console.

## The screen

```
 ◆ CLANK  paper   ● service up 2h  ● docker running  ● daily 262K  ● gateway  ⣾ working      02:09   header
 F4 This folder │ ┌─ Get ready to work here ─────────────────┐ ┌─ Machine ────────────────┐   machine
 1 Home         │ │  1  Docker            ✓ running          │ │ CPU  ███░░░░░░░░░░░  12% │   column
 2 Questions    │ │  2  This folder       ✓ ready            │ │      ▁▁▂▁▃▁▁▂▁▁▂▁▁▁▂     │   (F5)
 ...            │ │  ...                                     │ │ RAM  ...                 │
 menu           │ └──────────────────────────────────────────┘ └──────────────────────────┘
                │ page: each section a panel                   ┌─ Clank now ──────────────┐
                │                                              │ ⣾ agent · answering      │
                │                                              └──────────────────────────┘
 message line: what the last action did, or why it failed
 keys bar: the page's own keys, then ? explain  f1 help  f5 machine column  q quit              ^p palette
```

| Part | Where | What it shows |
| --- | --- | --- |
| Header | `clank/console/header.py` | Clank's name, the folder's name, a pill per part that runs (`PILLS`), each in its state's color, and dev mode's while it is on, whatever providers there are: "dev mode: any provider, any host" ("dev mode" when narrow; decisions 0149 and 0152: any cloud provider, and every public host for the agent, private addresses still never); a spinner while something runs. |
| Menu | `clank/console/app.py` (`_menu`), `clank/console/menu.py` (`PLANNED`) | Every page with its key, then the pages later milestones bring, in red. |
| Keys bar | `clank/console/keysbar.py` (`KeysBar`), `clank/console/keys.py` (`ANYWHERE`, `fit_keys`), each page's `KEYS` | The keys of the page on screen, then the keys that act anywhere, each a button; when narrow, `f5`, `q` and the palette go first, then the page's keys from the right, and `?` and `f1` always stay. Help (F1) and `?` read the same declarations. |
| Buttons | `clank/console/buttons.py` (`Buttons`, `button`, `lay_out`, `from_keys`) | Every key the console shows is a button (design 0011 §12): a group is one widget that takes the focus, a row or a column with its own cursor; a button pressed goes through the console's one door (`ClankConsole.press_button`), as its key typed does. |
| Pages | `clank/console/pages/`, and each component's `console/` package | One page each; the menu entry is the page's `ENTRY`. A page that reads the service on its own draws what came on the console's redraw ticks (`Page.tick`). |
| Machine column | `clank/console/machine.py` (`MachineColumn`) | Two panels: "Machine", the machine's meters (`MACHINE`), and "Clank now", what Clank is doing (`NOW`); each meter drawn for the inside of its panel, the blank lines between meters going first when the column is short, then the last meters, whole. |
| Drawing helpers | `clank/console/gauges.py`, `clank/console/text.py` | Bars, sparklines, sizes, rates, the spinner; times, counts, states in color. |
| Data | `clank/console/data.py` | Everything the console shows, loaded once and kept current from the event stream. |
| Look | `clank/console/clank.tcss` | Sizes, borders, what shows at which width. |
| Panel | `clank/console/panel.py` | A section of a page: a box with its title, and its note, in its top border; `PanelRow` sets panels side by side, each the row's height, stacked when the row is narrow or when what a panel holds asks for more room (`stack_below`); `PanelGrid` sets them in columns of set widths, one as tall as several beside it, stacked in the order given. |
| Windows | `clank/console/details.py`, `pick.py`, `form.py`; `ToolsScreen` (MCP servers), `TrafficScreen` (Phone) | Over the page, closed by Esc: each one panel, a `WindowPanel` (the traffic window two, its list and the highlighted exchange), its title in its border, its border in `border-focused`, its keys its last line; a title too long for the window is cut in the border and shown whole as the first line. |
| Setup | `clank/components/agents/console/setup.py`, `clank/components/agents/checklist.py` | `clank setup`'s checklist (design 0028 §4, decision 0148), the service's (`GET /setup`, the console's `setup` topic): each item with its mark, what it is now and what to do, the key that does the next step under them, or Ready's words; no key of its own (F11 is the terminal's full screen), the menu's last page, opened first while anything required is missing that This folder does not put right itself. |
| Phone | `clank/components/remote/console/phone.py`, `clank/components/remote/qr.py` | The page on F9 (design 0005 §5, design 0025 §2): remote access on or off (`x`), the paired devices and what each exchanged with the PC (Enter; `d` revokes one), the files sent. `p` makes a pair link for a device and draws its QR code as text (two modules a character), to scan with the iPhone's camera, with the link and the code under it, good for fifteen minutes; `c` cancels it, `p` again makes a new one. |
| Monitor | `clank/components/agents/console/monitor.py` | The page on F10 (design 0012): a row of tabs (F10 again moves to the next view), one heading line, and each view's panels, shown by the page's class; the machine column hidden on it (`Page.MACHINE_COLUMN`). It follows the folder's newest active session (`following.py`). The Watch for panel's marks (`watchfor.py`, design 0012 §8) and their count not seen beside "Monitor" (the page's `badge`). What the session does now (`nowpanel.py`, its spinner a cell of its own, turned on the page's ticks), its tool calls (`callspanel.py`, Enter reads one whole; it gives up rows first when the page is short), the live text (`livepanel.py`, `l`) and the growth spark (`contextpanel.py`). The context's parts (design 0012
§4.2): the bar by part and what each part holds (`parts.py`), Biggest in the context (`biggestpanel.py`, Enter an item
whole), and the Context view (`contextview.py`: the totals, What is in it, Where the room went, Where these figures
come from; `contextgpu.py`, On the GPU exactly; `contextchart.py`, Over this session; `contextfreed.py`, Could be
freed), each line no wider than its panel; a part's items, or what could be freed, in their window (`itemsscreen.py`),
where `x` drops the result highlighted through the Guide's Drop. It draws what its readings brought on the console's redraw ticks (`Page.tick`), so it redraws at most four times a second. The Flow view (`flowview.py`, design 0013 §12) shows the flow the folder follows (`GET /flows/view`): its boxes in rows of stages (`boxchart.py`, `boxpanel.py`), Selected with a Live box, Models in this flow, Waiting for you, The brief, checked, Deliverables and Ahead (`flowpanels.py`); its boards D2 (`e`, a box's settings), D3 (Enter on a gate) and D4 (Enter on a DECOMPOSE whose proposals wait, the cards) are `flowboards.py`'s; Enter on a running box opens its session in the Session view, Esc back to the box; Enter on Deliverables shows the file highlighted, `o` opens it in Clank's VS Code window; `h` the run log, `p` pause, `r` run from here (a flow not run yet, from its start); `n` builds a new flow with the model beside the console (This folder's `f` too), never in its terminal: over SSH the view says to run `clank flow attach` in another terminal, in Windows Terminal its window is split for it, in VS Code's terminal (or with `N`) Clank's VS Code window opens (design 0013 §15, decision 0100); while the planning is open the view draws it (decision 0101): the heading says which draft it shows, Building it with the model takes Selected's place with its steps and a Live box for its session, the latest draft is drawn marked DRAFT, and Enter opens its session in the Session view; a flow built with the model shows in Waiting for you with its check's warnings, wrapped. `clank console --page monitor --view flow` opens on the Flow view, for a terminal that keeps F10. The keys bar shows the keys of the view, or of the board, on screen (`Page.shown_keys`). |
| The session's flow | `clank/components/agents/console/flowtree.py`, `flowchart.py`, `flowpanel.py` | The flow as a tree (`tree`), laid out in lines for a width (`render`: branches to the right in aligned columns, under their node when narrow), and the Flow panel's widget of lines (`FlowChart`), which lays out again only the lines that changed. |
| Style | `clank/console/style.py`, `clank/kernel/console_kinds.py`, `clank/defaults/styles/clank.json` | The style's elements (colors, marks, glyphs), read at start and loaded as the console's theme. |

## Buttons: every key you see

Every key the console shows is a button (design 0011 §12, board K2): the keys bar's, This folder's next step, ways to
work and settings, a question's options, a window's keys. Each is pressed three ways, all the same: **Enter** or
**Space** while it has the focus, **its key** from anywhere on its page (the focus stays where it is), or **a click**
(the focus moves to it).

| Key | What it does |
| --- | --- |
| Tab, Shift+Tab | The next or previous group: the menu, the page's lists and rows of buttons, the keys bar; after the last, the first |
| ← → | In a row of buttons (the keys bar too), the next button, stopping at the row's ends; from the menu into the page and back, as before |
| ↑ ↓ | In a column of buttons, the next one; from a row, the group above or below (from the keys bar, back into the page) |
| Home, End | A row's first or last button |
| Enter, Space | Press the focused button; Enter on the menu goes into the page |
| Esc | Back: a step back inside a page when it has one (its keys bar says `esc back`), else to the menu; from a group, back to the page's main list; in a window, leave it; in a field, leave it first (decision 0151) |
| Backspace | Erases in a field you type in; never moves you, and no page has it as a key. A field's own keys (Backspace, Delete, the arrows, Home, End) never reach the page (`field_keys`, decision 0151) |
| ? | With a button focused, what it does and the keys that press it, or why it cannot act now |

While a group has the focus, the message line says what its focused button does. A dimmed button cannot act now
(This folder's `i` before the workspace is opened): it still takes the focus, so the message line and `?` say why,
and pressing it, or its key, says why instead of acting. A list keeps its own arrows (the menu, a page's list, the
Flow view's boxes): the arrows move between buttons only while a row of buttons has the focus. Clicks work over SSH
wherever the terminal sends the mouse (Windows Terminal, VS Code's terminal, OpenSSH; tmux with `set -g mouse on`).

## Changing the look

- **Colors**: the console's style (design 0011), a settings file whose colors are each named for what they color:
  `good`, `attention`, `failed`, `now`, `quiet`, `planned`, `border`, `selection`, and so on. The code and
  `clank.tcss` name only these, as `$clank-good`, never a fixed color, so changing the style changes them all.
  Clank's own style is `clank/defaults/styles/clank.json`, whose values are the kind's defaults
  (`clank/kernel/console_kinds.py`). Yours go in `CLANK_HOME/config/styles/<name>.json` and name only what they
  change (`{"schema": "style/1", "colors": {"good": "#00ff00"}}`); `CLANK_HOME/config/console.json` names the one in
  force (`{"schema": "console/1", "style": "<name>"}`). Ctrl+P's "Change style" lists the styles and writes the one
  picked there, through the service; the console draws in a style as soon as the service reports a change of
  `console.json` or of the style's file. A style that is not found gives Clank's; a file that does not read leaves the
  style in force (Clank's, at start), and the message line says why, with the file, line and field. Textual's own
  themes are not offered: the colors are the style's. A button's states have five colors of their own:
  `button_hover`, `button_focused` and `button_focused_text`, `button_pressed`, `button_unable_focused`.
- **Marks and glyphs**: the marks that say a state (● ○ ✓ ✗ ?), the header's ◆, the … that ends text Clank cut, the
  spinner's frames, a bar's cells and a sparkline's steps are the style's too (`marks`, `spinner`, `bar`, `sparks`).
  A page draws a mark by its name, `mark("done")` (`clank/console/style.py`), and the drawing helpers read the rest,
  so a style whose marks are plain (`"done": "+"`) changes every page, and `tone("+")` still colors it as done.
- **The check**: `tools/check_colors.py`, run with the tests, refuses a color or a mark written in the console's code
  (a hex color, `rgb()`, `red` in a rule or a style string, `[green]`, `$success`, a `"✓"`), naming the file and line;
  prose that names a color passes. `uv run python -m tools.check_colors` runs it alone.
- **Sizes and layout**: `clank.tcss`. Your own rules go in `CLANK_HOME/config/console.tcss`, loaded after Clank's, so
  they win; the console reloads it as soon as you save it. For example, a wider machine column: `#machine { width: 44; }`.
- **When the machine column shows**: from `MACHINE_FROM` columns (130) in `app.py`, by the screen's `-wide` class; F5
  shows or hides it at any width.
- **When a bar takes the style's `busy` or `full` color** (yellow or red in Clank's): `BUSY` (60%) and `FULL` (85%)
  in `gauges.py`.
- **How states are colored**: the words in `GOOD`, `CHANGING` and `BAD` in `text.py` (`tone`, `painted`) take the
  style's `good`, `attention` and `failed`.

## Adding things

- **A meter in the machine column**: a function `(seen: Seen, width: int) -> list[Content]` in `machine.py`, added to
  `MACHINE` (or to `NOW` for what Clank does); `width` is the inside of its panel. `seen.readings` holds the last five
  minutes of readings, oldest first; `named`, `gauge` and `below` draw a meter's lines; `spark` and `bar` come from
  `gauges.py`. A new value the service should read goes into `Meters.read` in `clank/components/machine/meters.py`.
- **A pill in the header**: a function `(data, activity, now) -> Said | None` in `header.py`, added to `PILLS`;
  `Said(words, short, state)`: the short words are used when the header is narrow, the state colors the pill.
- **A page**: a `Page` subclass with an `ENTRY` (`MenuEntry(id, label, summary, designed_in, key=...)`), `compose`,
  `draw(data, changed)` (only the parts whose topics changed), `press(key)` and `explain()`; a component lists its
  pages in its `console()`. The page declares its keys once, most used first, in `KEYS`
  (`PageKey("s", "docker", "start or stop Docker")`: the key, the action's name, its words), which the keys bar, Help
  and `?` read, so a page writes no line of hints; `PageKey`'s fourth field is what Help says when the words are too
  short to say it alone. A page that runs work of its own sets `busy` and draws its spinners in `spin(frame)`.
  `compose` yields each section as a panel, `with Panel(title="Containers", id="docker-containers-panel"):` (its
  title as the page's board writes it, design 0011 §8; a list gets a panel too), and the page lists its panels' ids in
  order in `PANELS`. Panels the board sets side by side go in a row: `yield PanelGrid(Panel(...), Panel(...),
  columns="2fr 1fr", stack_below=80)` (Home's Happening now beside Waiting for you), which stacks them, in reading
  order, when the row is narrower than `stack_below` columns; a page sets `stack_below` anew when what a panel holds
  asks for more room (Home's, while a question waits), and the row stacks at once. A panel's id is the prefix its page's widgets' ids share (`docker`; `mcp` on MCP servers,
  `completion` on CPU models) and what it shows (`workspaces-highlighted`, `models-switches`), with `-panel` added
  only when a widget inside already has that id (`docker-containers-panel` holds `#docker-containers`); Home's panels
  keep the ids its sections had (`now`, `runs`, `waiting`, `history`), and a planned page's one panel is `planned`. M2's
  layout file will name panels by these ids, so a panel keeps its id. A count or a name goes where the page's board
  draws it: in the title, which a page may change (`panel.title = f"Details · {name}"`, "Waiting for your answer ·
  2"), or as the note at the right of the top border (`panel.note = "4 workspaces, 1 running"`), which a narrow panel
  drops first. A panel is never narrower than its title, and a page narrower than one of its panels (F5's machine
  column in a narrow window) scrolls sideways to all of it (`Page`, design 0011 §9).
  `tests/console/test_panels_everywhere.py` checks that each page draws the panels it declares, each with its four
  borders and its title whole, and nothing outside them, and that it scrolls sideways to every panel wider than it.
  `tests/console/test_keys_bar.py` checks every page's `KEYS` and that Help lists them. Keys a panel offers are
  buttons: `Buttons(from_keys(self.KEYS, "o", ("a", "OpenCode in this terminal")))`, its keys chosen from
  `KEYS` (a longer sentence for the panel when given), `column=True` for a column, `lead="Next:"` for words before
  them; nothing more is needed, since a button pressed goes to the page's `press` like its key. A key that cannot
  act now says why in the page's `unable(key)` ("" when it can): its buttons dim, and the key says why.
- **A window**: a `ModalScreen` whose `compose` yields one `WindowPanel(*lines, Label("Esc closes this.",
  classes="hint"), title=..., id=...)`, its keys its last line (or, as the details window and a window that asks
  first do, a `Buttons` of its keys with `press=` its own action, so the focus starts on its first), and its screen's
  name added to the rule that centers the windows in `clank.tcss`. `tests/console/test_windows.py` checks each window.
- **A topic the console follows**: in `data.py`, its name in `TOPICS`, its path in `PATHS` (or `fetch`), and in
  `touched` the events that change it; a live event becomes an `Update` in `Follower._receive`.

## Seeing it

- **Tests**: `tests/console/`; frames are compared with `tests/console/snapshots/` (`CLANK_UPDATE_SNAPSHOTS=1`
  rewrites them; review the diff). Console tests read a fixed machine reading (`READING` in
  `tests/console/conftest.py`) and show a fixed folder (`FOLDER`), so frames are the same on every machine. The
  console works in its own time, so a test waits, with `tests/console/frames.py`: `settle` until a condition holds,
  `steady_frame` for a frame that stopped changing, `frame_when` for one that shows given words, and `focus_on` to
  move the focus. A test reads what shows in the frame (`render_text`), since a hidden label still holds its text.
- **A picture of a frame**: run the console headless with `ClankConsole(...).run_test(size=(W, H))`, save
  `app.export_screenshot()` as an SVG, and open it in a browser (or turn it into a PNG with a headless browser).
