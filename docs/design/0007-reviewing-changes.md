# Design 0007: reviewing the agent's changes in VS Code

The owner (2026-10-14, again 2026-10-15): "when it makes changes I want to actually see those changes pop up in the
region where I can look at the code ... toggle on and off the auto-mode ... keep the model from writing any code
without me reviewing it ... it may require an extension". Design 0002 named the modes (plan, auto, ...) and made every
ask to the user a question (§2.5); design 0005 §2 gave the service a bridge to the OpenCode servers in a workspace's
container.

**Status:** written 2026-10-15, every section *proposed*, built as proposed at the owner's instruction ("do VS Code
review mode next"); **Choice** marks what the owner may decide otherwise.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Proposed 2026-10-15 |
| 2 | How OpenCode asks, as measured | Proposed 2026-10-15 |
| 3 | Review and auto: Clank answers | Proposed 2026-10-15 |
| 4 | The watcher | Proposed 2026-10-15 |
| 5 | A change | Proposed 2026-10-15 |
| 6 | VS Code | Proposed 2026-10-15 |
| 7 | The console and the phone | Proposed 2026-10-15 |
| 8 | What review does not cover | Proposed 2026-10-15 |

## 1. What the owner gets

Each workspace is in one of two modes, **review** (the default) or **auto**:

- **Review.** Before the agent changes a file, the change opens in VS Code's editor beside the agent: the file as it is
  on the left, as the agent would leave it on the right. **✓ Accept** in the editor's title bar lets the agent go on;
  **✗ Reject** keeps the file as it is and tells the agent no, with a note when the owner writes one ("keep the old
  name"). The agent waits until then. The same change can be answered from the agent's terminal, the console or the
  phone; whichever answers first, the others close.
- **Auto.** The agent changes files without waiting; each change still opens in the editor (the file before and after,
  in a preview tab that the next change reuses, without taking the keyboard), so the owner sees what it did.

The status bar shows the window's mode (**Review** or **Auto**); a click switches it. The console's This folder page
shows it too (`r` switches). Every change, its answer and who gave it are kept (§5).

## 2. How OpenCode asks, as measured

Measured on 2026-10-15 with OpenCode 1.19.0 in the sandbox image, a scripted model and no network:

- With `"permission": {"edit": "ask"}`, the edit and write tools ask before they write: `permission: "edit"`, the file
  (`metadata.filepath`), a unified diff (`metadata.diff`), and the tool call (`tool.messageID`, `tool.callID`). The ask
  arrives on the server's event stream (`GET /event`, `permission.asked`); the answer too (`permission.replied`), from
  whichever client gave it, and then `file.edited` once the file is written.
- **The diff cannot be applied as it is**: OpenCode removes the indentation its lines share (for its terminal's
  display), on the ask and on the finished tool alike.
- `POST /permission/{id}/reply` takes `once`, `always` or `reject`, and with `reject` a `message`: the model receives it
  ("The user rejected permission to use this specific tool call with the following feedback: ...").
- **Changing the configuration while OpenCode runs does not change whether it asks** (`PATCH /config` with `edit:
  allow` was accepted; the next edit still asked), and it restarts OpenCode's instance, closing every event stream.

## 3. Review and auto: Clank answers

Since OpenCode cannot switch while it runs (§2), the agent always asks (`edit: ask` in the configuration Clank writes),
and **Clank answers**: in auto mode at once, as "Clank (auto mode)"; in review mode it asks the owner, as a question
(design 0002 §2.5: an approval with Accept and Reject, about the change) and answers OpenCode with what the owner chose.
The mode is the workspace's (its record's `changes`), so switching applies to the very next change, in every agent
running in the container, the phone's included.

Clank answers `once`, never `always`: an `always` would stop OpenCode asking for the rest of its run, and auto mode
could not be switched back. (The agent's terminal still offers "Allow always"; chosen there, that agent stops asking
until it restarts.)

## 4. The watcher

The service keeps one watcher for each running workspace container: the bridge's `watch` action (`docker exec`, one
process, kept open). In the container it follows the event stream of every OpenCode server on the bridge's ports
(servers that start later too, every two seconds) and writes one JSON line for each thing the service needs:

| Line | When |
| --- | --- |
| `asked` | A permission is asked (the ones waiting when a server is first followed too); for a change, with the tool call's input |
| `replied` | A permission was answered, by anyone |
| `edited` | A file was written |
| `gone` | A server stopped |
| `synced` | Every server running when the watcher started has been read |
| `alive` | Every 15 seconds |

The watcher ends when its input closes (the service stopped or the exec was ended), and replaces an older one left in
the container. The service starts it from the Docker state its background check already reads (no extra Docker calls)
and starts it again if it ends while the container runs. Nothing polls: the service hears of a change as it is asked.

A container made from an image before the watcher cannot be watched: its agent still asks, in its terminal, and the
This folder page and VS Code say to reopen the workspace (F6: `x`, then `o`) to review in the editor.

## 5. A change

When a change is asked, the service reads the file from the folder (the container's `/workspace` is the folder) and
works out the file as the agent would leave it: from the tool call when it applies exactly (a write's content; an edit
whose old text is found once, or everywhere when it replaces all), else from OpenCode's diff, its lines placed by their
numbers and their indentation restored from the file; a change it cannot work out shows OpenCode's diff as it is. The
change is kept in `state/changes/` (the newest 200): the file before and after, the diff, the mode, the answer, who gave
it and when, and, once written, the file as it was written.

Its events: `agents.change_proposed`, `agents.change_answered` (accepted or rejected, by whom: the owner through a
client, the agent's terminal, auto mode) and `agents.change_made` (the file was written).

## 6. VS Code

The extension (0.3.0) follows the events it already follows:

- A question about a change in the window's folder opens as a diff in the editor group of the files, never over the
  agent's terminal, without taking the keyboard. Its title bar has **✓ Accept** and **✗ Reject**; Reject asks for an
  optional note (Escape cancels the reject). When the question is settled anywhere, the diff closes; one settled while
  the window is still reading its change never opens, and when the window connects (after a reload too) a diff left
  open whose question no longer waits closes. It is not shown as a notification, as other questions are.
- In auto mode each change made in the window's folder opens as a preview diff (the setting
  `clank.changes.showInAuto`, on by default).
- The status bar item **Review** / **Auto** shows the mode of the window's workspace, with a tooltip that says what it
  means; a click switches it. Commands: `Clank: Accept the change`, `Clank: Reject the change`, `Clank: Switch between
  review and auto`.

## 7. The console and the phone

A change waiting is a question like any other: the Questions page shows it (`v` shows its diff, `y` accepts, `n`
rejects) and the header counts it. The This folder page shows the workspace's mode, and `r` switches it. The phone shows
the question with its diff, and no longer lists the agent's own ask for the same change beside it.

## 8. What review does not cover

- **Commands.** Review covers the agent's file tools (edit, write). A command the agent runs in the container (a script
  that writes results, a formatter) still changes files without asking, as before; the sandbox bounds it to the folder.
  **Choice**: commands could ask too (OpenCode's `bash` permission), which would make the agent stop at every `ls`.
- **The service.** Clank answers only while its service runs. When it does not, the agent asks in its terminal, which the
  owner can answer there, in either mode.
