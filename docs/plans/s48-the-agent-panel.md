# Plan s48: the agent panel

Builds [design 0021](../design/0021-all-llm-work-in-clank.md) §4, approved by the owner on 2026-10-25: Clank's own view
of the agent in VS Code, beside OpenCode's terminal, on the same session through the session bridge, so the owner can
read the conversation drawn (Markdown, math, the thinking and each call folded, images, artifacts as cards), answer
what waits, and write to the agent, and switch to the terminal at any moment. Each task starts with a failing test;
each ends with a commit pushed to `main`.

## How it works

- **One route composes the conversation** (`GET /agents/conversation?folder=&session=&limit=&before=`): the folder's
  workspace, its session (the one named, else the newest the service keeps a flow of, else the newest root session a
  server of the workspace lists, so a panel opened after the service restarted still has one), the server that reaches
  it, a page of its messages in the Monitor's shape (design 0012 §6.1, as the bridge reads OpenCode's history, oldest
  first, with the cursor of the page before), whether it is busy, and the permissions and questions waiting in it.
- **The panel draws it** (`core/conversation.ts`, pure): the owner's messages, the model's text as Markdown with its
  math (marked and KaTeX, the artifacts' libraries, decision 0135), its thinking folded, each tool call folded with its
  state, title, input and output, an image the agent showed or looked at inline, an artifact it made as a card that
  opens it (§5), and what waits with its buttons. Code is set in monospace without highlighting (a highlighter would be
  a new dependency, decision needed).
- **Where it is**: a webview tab in the agent's group, beside OpenCode's terminal, opened by `Clank: Show the agent
  panel` and by the status item's menu; the terminal stays in front unless the owner picks the panel. The readout
  stays under the group (§3), since the panel and the terminal share it.
- **Writing**: the input sends to the session (`POST .../message`); `@` lists the folder's files and puts the chosen
  one's path as the agent sees it (`/workspace/...`); an image pasted is saved in the folder (`.clank/pasted/`) and its
  path put in the message, for the agent to look at (§9). Stop, Compact and New session are the Guide's and the
  sessions' routes; Show in terminal shows the panel's session in OpenCode's window.
- **Kept fresh**: the panel reads the route every two seconds while the session is busy, every eight while it is not,
  and only while it shows (as the phone does).

## Tasks

- [x] 1. **The conversation route**: `Agents.conversation(folder, session, limit, before)` and
  `GET /agents/conversation`; `Sessions.reach(workspace, session)` (the server that runs the session, else one that
  lists it, else the first that runs; the artifacts' comment uses it too); a folder with no workspace, or a workspace
  with no session, answered as such. Tests with a fake bridge: the session chosen (named, kept, listed), its page and
  cursor, its waits, busy.
- [x] 2. **Drawing it** (`core/conversation.ts`): messages to items (owner, text, thinking, call, image, artifact card,
  wait), each call's one-line summary, a page's items merged with the next reading (no flicker, the open folds kept).
  Node tests.
- [x] 3. **The panel in VS Code** (`src/agentPanel.ts`, `media/agent.{html,js,css}`): opened beside the terminal, drawn
  with marked and KaTeX from `media/lib`, read while it shows; folds, images (the folder's files through the webview),
  artifact cards opening the artifact's panel, older pages on scrolling up.
- [x] 4. **Writing and acting**: the input (Enter sends, Shift+Enter a new line), `@` files, a pasted image saved,
  Stop, Compact, New session, Show in terminal, and the waits' buttons (allow once, always, reject; a question's
  answers). Node tests for what the core decides; the routes' tests for the service's part.
- [x] 5. **Live**: the real model, in a throwaway folder: the conversation drawn while it works, a message sent from the
  panel, a permission answered, an artifact card opened, seen in a screenshot of that window only.

## Progress

Written 2026-10-25.

- Tasks 1-5 built 2026-10-25/26 (0.9.8 ff9c15d; restyled as direction A, the owner's choice, 0.9.9 c934c04: theme tokens
  following VS Code or Clank Night). Live, in the owner's window with the real model: the conversation drawn while it
  worked, a message sent from the panel. Seen then: repeated Thinking rows, the header saying idle while the model read
  the prompt, the readout's line twice; and every read through the bridge, three seconds behind. Design 0023 (talking
  to the agent) takes those up with the stream; the items of the design canvas's "A · full design" (jobs tray, merged
  thinking, live output, artifact previews, LaTeX card, question choices, change review, start page, Build and Plan,
  the narrow layout) are built on it, not on the polling.
