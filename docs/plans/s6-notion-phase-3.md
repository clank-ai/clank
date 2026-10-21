# Notion, phase 3: implementation plan

> At the owner's request (2026-10-17): "go ahead and start phase 2, and just immediately test things and commit and
> push to github, and move on to phase 3. We will wait to implement phase 4 until after everything else is done." As
> for the plan mode's plans, the files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** design 0010 §11, phase 3: comments, and sending a batch back (§7): the owner comments on a batch, an entry,
a property or a block of its page; the batch goes back to the agent that staged it with every comment in words; the
agent revises it with the same tools and answers each comment (`notion_reply`); the review shows the revision and the
answers; approving over unanswered comments asks first.

**Spec:** [design 0010](../design/0010-notion.md) §7.

## Global Constraints

- Never the owner's Notion, and never a real agent in the tests: the service's tests use the fake Notion and a fake
  agent link; the extension's use a fake API and headless Edge.
- No comment's words in an event; commenting and sending back are the owner's (`403` for the agent, and the gateway
  forwards only the agent's answer).
- The owner is the sole author of every commit; American English; tests named as sentences.

## Tasks

- [x] **Comments:** `comment` (the batch, a proposal, a property, or a block: a change's block of its page's changes,
  a new entry's paragraph; the block's Markdown kept with it), `uncomment` (only one not sent), on the batch; a batch
  in brief counts them (`comment_counts`) (`clank/components/notion/comments.py`;
  `tests/components/notion/test_comments.py`).
- [x] **Sending back:** `send_back`: one message (`comments.message`: each comment with what it is about, what to
  do) to the session that submitted the batch (kept at `submit`), else a new session in the workspace's OpenCode
  window (`agent.py`, through the agents component; `Modes.window_port`); the batch *returned*.
- [x] **Revisions and answers:** while a workspace has a batch sent back, its agent stages into it: a proposal for
  the same entry (or a new entry of the same title) replaces the one there, keeping its number and what it was
  (`previous`), unless anything of it is written; `submit` makes the next revision; `reply` answers a comment.
- [x] **The agent's way in:** the gateway forwards `POST reply`; Clank's MCP server gets `notion_reply`
  (`tests/components/gateway/test_notion_forwarding.py`, `tests/components/agents/test_notion_tools.py`).
- [x] **The routes and the command line:** `POST|DELETE notion/batches/<id>/comments[/<c>]`, `POST
  notion/batches/<id>/return`, `POST notion/reply`; `clank notion comment|send-back`, comments in `show`.
- [x] **VS Code:** the page's threads and composers on the batch, each entry, each property and each block, the counts
  in the table, **Send back with N comments**, what a revision changed; the view keeps a batch sent back (not
  counted); approving over unanswered comments asks first (`vscode/test/notion.test.ts`,
  `vscode/test/notion.page.test.ts`); the extension 0.8.0.
- [x] **Documents:** design 0010 (*as built*), this plan, the setup guide, the extension's README.
