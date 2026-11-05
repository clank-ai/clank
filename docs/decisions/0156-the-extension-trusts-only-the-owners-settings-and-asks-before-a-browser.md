# 0156. The VS Code extension trusts only the owner's settings and this machine's service, and asks before a browser

- Status: Accepted (the audit of 2026-10-30); revises design 0002 §2.7, design 0004 §5 and design 0021 §5; its guard
  on Open in browser completed by 0165 (the page in a sandboxed frame)
- Date: 2026-11-04

## Context

- The extension's settings `clank.home` (which CLANK_HOME, so which service it connects to) and
  `clank.agent.openOnStart` (whether it starts the agent when a window opens) had VS Code's default window scope, so a
  folder's own settings could set them, in Restricted Mode too. The extension trusted any address in the connection
  file, and ran the program the service answered in the agent's terminal.
- An artifact's page and Clank's bar over it share the webview's messages, so a message cannot be told from the
  owner's click; Open in browser opened the export without a question.
- The full fix of the second, the page in a sandboxed iframe that cannot reach the extension, is a larger change and
  comes later; this is the step before it.

## Decision

- **The two settings are the owner's alone.** `clank.home` and `clank.agent.openOnStart` have `machine` scope: VS Code
  reads them from the user's settings (in a remote window, the remote machine's), never a workspace's or a folder's.
  The manifest declares `untrustedWorkspaces: { supported: "limited" }` with both under `restrictedConfigurations`. The
  extension also reads only their user value (`userSetting`, VS Code's `inspect`), so a folder's value is ignored
  whatever VS Code does with scopes. Clank's own window writes `clank.agent.openOnStart` in the instance's user settings
  (and, from Remote-SSH, the server's machine settings), so it keeps working.
- **Only a service on this machine is trusted.** The extension connects only to `http://` at `127.0.0.1`, `localhost`
  or `[::1]` (any port, no user name), the names the service listens and answers on (§2.7). Any other address in the
  connection file is refused with a warning naming the file and the address, said once, and the local token is never
  sent to it.
- **The agent's terminal runs only Clank's programs**: `docker`, `wsl` or `ssh`, named alone or by a full path, with
  or without `.exe` (`terminalProgram`). Today the service always answers Docker's command. Any other program is
  refused, and the agent's place says which program was named and what the terminal runs.
- **A version opens in the browser only after the owner says so.** A 'browser' message from the artifact's panel
  asks first, in VS Code's own modal question, naming the artifact's title, name and version; only the answer **Open
  in browser** exports the version and opens it. A panel asks one question at a time, and asks nothing for 3 seconds
  after each answer, so a page cannot keep the question in front of the owner.
- **An export carries the webview's content policy**, before anything in the page but its doctype: no address of any
  kind, its libraries and files inside it (`data:` and `blob:`), inline scripts and `eval` as in VS Code, no form
  submitted and no `<base>`. In a browser too it reaches nothing on the network.

## Alternatives considered

- **`application` scope** in place of `machine`: it would ignore the remote machine's settings, where Clank's window
  from Remote-SSH writes `clank.agent.openOnStart` (design 0018 §8).
- **Declare no support for untrusted folders**: the extension would not run in Restricted Mode at all, though it reads
  nothing from the folder that it needs to trust once the two settings are the owner's.
- **Check the service's process or a signed address** in place of the loopback check: the local token already proves
  the caller to the service; what the extension needs is that it never sends that token, or follows an answer,
  anywhere but this machine.
- **Open the export only from a click Clank alone can see** (the sandboxed iframe): that is the full fix, which comes
  later; until then a question VS Code asks, outside the page, is the one answer the page cannot give.

## Consequences

- A folder, a cloned repository or a file the agent wrote can no longer choose which service the extension trusts,
  which program it runs or whether it starts the agent. The owner who sets `clank.home` sets it in the user settings,
  as the setting's description now says.
- A service on another machine, or behind an address other than these three, is not reached from VS Code; it never
  was by design (the service answers only to these names).
- Open in browser takes one more click, until the page moves into a sandboxed iframe that cannot send the bar's
  messages.
- A program Clank one day starts the agent with other than these three is added to `TERMINAL_PROGRAMS`, with its test.
