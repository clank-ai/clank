# Design 0010: Notion, read freely and changed only after review

The owner asked (2026-10-17) for data kept in Notion databases to be shared with others more quickly, with
transparency first: the local model reads the databases freely and stages each change, addition or removal it wants to
make; the owner previews and approves them elsewhere, in a VS Code extension, and can annotate them with comments and
send them back to the model. The owner sets Notion up, and the content stays with the local models.

**Status:** written 2026-10-17, every section *proposed*, built at the owner's instruction ("begin the design and start
implementing this immediately"), in the phases of §11. **Phase 1 built 2026-10-17** ([its plan](../plans/s4-notion-phase-1.md)):
the connection, reading, staging, applying, the agent's tools through the gateway, and `clank notion`; what it settled
is said in its sections (*as built*). **Phase 2 built 2026-10-17** ([its plan](../plans/s5-notion-phase-2.md)): the review
in VS Code, as mockup D, and approval in parts. **Phase 3 built 2026-10-17** ([its plan](../plans/s6-notion-phase-3.md)):
comments, sending a batch back, revisions and the agent's answers. **Choice** marks what the owner may decide otherwise. The review
in VS Code follows the owner's pick among four mockups (2026-10-17): the database's table with its changes marked, and
under it the chosen entry's fields, page and preview, with comments.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Proposed 2026-10-17 |
| 2 | The Notion side, set up by the owner | Proposed 2026-10-17; built (phase 1) |
| 3 | Only the service talks to Notion | Proposed 2026-10-17; built (phase 1) |
| 4 | Reading | Proposed 2026-10-17; built (phase 1) |
| 5 | Staging | Proposed 2026-10-17; built (phases 1 and 3) |
| 6 | Review in VS Code | Proposed 2026-10-17; built (phases 2 and 3) |
| 7 | Comments, and sending a batch back | Proposed 2026-10-17; built (phase 3) |
| 8 | Applying | Proposed 2026-10-17; built (phase 1) |
| 9 | The command line, the console and the phone | Proposed 2026-10-17; the command line built (phase 1) |
| 10 | Privacy, and how it is tested | Proposed 2026-10-17 |
| 11 | Phases | Proposed 2026-10-17 |

## 1. What the owner gets

The owner keeps databases in Notion and shares them with others: for example **Papers** (a page of notes per paper,
keywords) and **Concepts** (notes, links into the papers down to sections and equations, the script that computes
each), then a database of results and one per project, which refer to the others. Clank's local agent works with them:

- **It reads them freely**: the databases, their entries, an entry's page as Markdown, a search.
- **It never changes them itself.** What it would add, change or remove it *stages*, as a batch with its reason and
  the sources of every number. The batch waits for the owner in VS Code, shown like a code review but for databases.
- **The owner approves** all of it, some entries, or some fields; **rejects** it with a reason; or **comments** on an
  entry, a field or a block of a page and **sends it back**, and the agent revises it. Nothing reaches Notion unless
  the owner approved it.
- **Whoever the owner shares the databases with sees only what was approved**, with the sources the agent gave kept
  on the entry.

## 2. The Notion side, set up by the owner

The owner sets Notion up alone (no Claude Code involved); `docs/notion-setup.md` is the step by step guide:

1. In Notion, create an **internal integration** named Clank, with read, insert and update content; copy its secret.
2. `clank notion connect` (or the console, §9) asks for the secret without showing it, keeps it as a secret
   (`CLANK_HOME/secrets/notion/notion/token`, design 0002 §2.8) and checks it (`GET /v1/users/me`).
3. **Share** each database with the integration (its ••• menu, Connections). Clank sees only what is shared.

Clank assumes no layout: it reads each shared database's properties and their types from Notion (its data sources,
§3) and works with whatever the owner builds, so databases can change and new ones (each study's) can be added at any
time. The guide suggests a layout (Papers and Concepts) as a start, never required.

**Choice**: one connection for the whole machine, every workspace's agent able to read every shared database
(default; the owner shares only the databases the agent may read); later, a workspace may be limited to some of them.

*As built (phase 1):* the component `notion` (`clank/components/notion/`); the secret is `notion/notion`'s `token`;
`clank notion status` says which integration and workspace the secret reaches, and `clank notion databases` what it
can see, so the owner can check their sharing before the agent works.

## 3. Only the service talks to Notion

The agent's container still reaches nothing but the edge (design 0004 §3). The path is:

agent → Clank's own MCP server in the container (`clank`, design 0005 §3: new tools, §4-§5) → the gateway, through the
edge (`/notion/...`, beside the model's routes) → the service (`/notion/...`) → `api.notion.com`.

- The gateway forwards these requests to the service with the token it already holds for the service's routes; the
  container never holds the Notion secret or the service's token (design 0002's rule for the GitHub token).
- `api.notion.com` is the service's one new outside host: the first host of M7's grants, granted to the service, not
  to a sandbox. Requests use `Notion-Version: 2025-09-03`, in which a database holds one or more **data sources**:
  entries are queried and created in a data source, and relations name data sources.
- Notion's rate limit is respected: one request at a time per connection, a `429` waits its `Retry-After`.
- Every read and write is recorded as an event that says what was asked (database, entry ids, counts), never the
  content.

*As built (phase 1):* the gateway's `/notion/` forwards `GET databases`, `POST query`, `GET page/<id>`, `GET search`,
`POST propose/entry|change|removal` and `POST submit`, as the client `agent`, which the service records as the agent's
session; anything else under `/notion/` is `403`, and the service refuses an approval or a rejection from the agent
too. Clank's MCP server names its workspace (`CLANK_WORKSPACE_NAME`) in every proposal. A `429` is waited out five
times at most, each wait a minute at most.

## 4. Reading

Tools of Clank's MCP server, answered by the service, results kept small for the model's context:

- `notion_databases()`: the shared databases, each with its data sources and their properties (name, type, the
  options of a select, the data source a relation points to).
- `notion_query(database, filter?, sorts?, limit?, cursor?)`: entries as compact rows: id, title, each property's
  value as plain text (a relation as the titles it points to), and a cursor for more.
- `notion_page(page)`: an entry's properties and its page as Markdown (headings, paragraphs, lists, equations, code,
  quotes, callouts, images as `![caption](notion:<id>)`, links to other entries as `[title](notion:<id>)`), paged when
  long.
- `notion_search(text)`: entries and databases whose title matches.

Reads need no review. *As built (phase 1):* the planner may use the four reading tools, never the proposing ones; a
page reads whole, four levels of children deep and 1,500 blocks at most, a toggle as `- ▸ ` with its contents
indented.

## 5. Staging

The agent proposes with these tools; each takes `why` and `sources` (the files, sections and scripts the content comes
from: required whenever it states a number):

- `notion_propose_entry(database, properties, page?)`: a new entry, its page in Markdown.
- `notion_propose_change(page, properties?, page_markdown?)`: new values for some properties; the page as it should
  be after the change (Clank compares it with the page now, block by block).
- `notion_propose_removal(page, why)`: the entry to the trash.
- `notion_submit(summary)`: the batch is ready for review.

A **batch** belongs to a workspace and to the agent's session that staged it (the watcher, design 0007 §4, sees the tool
call in its session). A session has one open batch; proposals before `notion_submit` gather in it. Each proposal is
checked when staged and refused with the reason, so the agent can fix it: the properties exist and each value fits its
type; a select's option exists (a new one is allowed but marked for the owner); a relation points to a shared entry or
to one proposed in the same batch; an image is a file in the folder; the Markdown converts. Each proposal keeps the
entry as it was when staged (its properties and page), the base the review compares with and that §8 checks.

*As built (phase 1):* batches are JSON files in `CLANK_HOME/state/notion/batches/` (open, ready, then written, partly
written or rejected). Each proposal must say why; numbers need sources (any digit in what it sets or adds). A
status's options are the owner's alone (Notion cannot add one from a page); a relation names an entry by its title or
id. Not yet: an image from a file (phase 4), a page nested more than three levels deep, and a block only Notion has
(a line Clank writes for one stands for it, kept when the page around it is). A change keeps only the fields it
changes, and its page as a list of block changes, a block changed in place when its kind and children stay.

## 6. Review in VS Code

- **The Notion changes view** (its own icon in the activity bar, the count of what waits on it): each batch waiting,
  with the agent's summary, its session, when, its revision, **Approve all**, **Reject all…** and **Send back with N
  comments**; under it each database with its counts (new, changed, removed) and its entries, each marked A, M or D.
- **The review editor**, opened from a database or an entry: the database's **table**, its changed rows and their
  neighbors (or all rows), each changed row marked (+ new, ~ changed with the old value struck above the new one, −
  removed) with a checkbox; and under it the chosen entry: **Fields** (in Notion now, proposed, a checkbox per field),
  **Page** (block by block, additions and removals marked) and **As in Notion** (how it will look), the sources the
  agent gave, and its comments (§7).
- **The status bar** shows "Notion: N changes waiting" and opens the view.
- **Approve** writes the checked rows and fields of the batch now (§8); what is unchecked stays staged until approved,
  rejected or sent back. **Reject…** asks for a reason, closes the batch and tells the agent.

*As built (phase 2):* the view is "Notion changes" in the activity bar (its badge and the status bar's item count the
proposals waiting); each batch waiting has **Open the review**, **Approve all** (asked first) and **Reject…** beside
it, and the batches written or rejected are under **Earlier**. The page shows one database at a time (a tab for each
when a batch touches several); everything not written is checked at first; a row's checkbox takes all its parts, and
the Fields and Page views check each property and the page alone. **Approve N checked** writes what is checked of the
database shown, **Approve this** of the entry chosen. A new entry is made with its title, so the page keeps its title
checked while any other part of it is. The page keeps the owner's choices when the batch is shown again (after an
approval, or an event), and marks what is written. The service gives each database as a table
(`GET notion/batches/<id>/tables`: the changed rows and one neighbor on each side, or every row with `everything`, a
thousand at most), and Notion's own address is the only link the page opens.

## 7. Comments, and sending a batch back

- A comment belongs to the batch, an entry, a field or a block of a page; it shows where it was made, and its entry is
  marked in the table.
- **Send back to the agent** marks the batch *returned* and sends the session that staged it one message: each comment
  with what it is about (entry, field or block, and the proposal there). A busy session gets it when it is idle; a
  session that is gone is replaced by a new one in the workspace's OpenCode window, given the same message.
- The agent revises with the same tools, making the batch's next **revision**; the review shows what changed since the
  last one, and each comment as answered or open (`notion_reply(comment, text)` answers one).
- Approving a batch with open comments asks first.

*As built (phase 3):* a comment is on the batch, a proposal, any property of its entry (changed or not), or a block of
its page (a change's block of its page's changes, a new entry's paragraph), whose Markdown is kept with it. The owner
takes back a comment until it is sent. The session that submitted a batch is the one most recently active in the
workspace when it was submitted (an MCP server does not know its session); a batch sent back goes to it while it runs,
else to a new session in the workspace's OpenCode window, and none is sent while no window runs (the owner is told).
The message lists each comment not sent yet, and those sent before and still unanswered, with what it is about in
words, and says what is written already. While a workspace has a batch sent back, its agent stages into it: a proposal
for the same entry (or a new entry of the same title in the same database) replaces the one there, keeping its number
and what it was, unless anything of it is written (then it is added); `notion_submit` makes the next revision.
`notion_reply` answers a comment of the workspace's newest batch that has it. The review shows each thread under what
it is on, with the agent's answer, the counts in the table, **Send back with N comments**, and what a revision
changed; a batch sent back stays in the view, waiting for the agent, and is not counted. `clank notion comment` and
`clank notion send-back` do the same from a terminal. No event holds a comment's words.

## 8. Applying

- On approval the service writes in order: new entries first (so relations to them can be written), then changes,
  then removals (to Notion's trash, where the owner can restore them). A changed page has only its differing blocks
  replaced, so the rest (and comments made in Notion on them) stays.
- **An entry changed in Notion since it was staged** is not written: the review shows it with Notion's new state, to
  approve again or send back.
- **Each entry's result is kept**: written (with its Notion link) or the error. A batch stopped halfway shows what was
  written; approving again writes the rest, never an entry twice.

*As built (phase 1):* approval takes the whole batch or some proposals (`--only p1,p3`). *Phase 2:* or some parts of
them (`parts`: properties by name, `page`, `removal`); what is written of a proposal is kept on it (`done`), and its
next part is checked against the entry's last edit after Clank's own write, so an edit in Notion between two parts
is still seen. A new entry is made with its title; its other parts are written to it later. A relation to a proposal not written yet refuses that proposal until it is. Pages are written a
hundred blocks a request; what Notion only answers (a run's `plain_text` and `href`) is never sent.

## 9. The command line, the console and the phone

`clank notion connect`, `clank notion status` (the connection, the shared databases, what waits), `clank notion
batches`, and `clank notion approve|reject <batch>`: usable before VS Code's review exists and as its backup. *As built
(phase 1):* also `clank notion databases` (what the integration can see) and `clank notion show <batch>` (each
proposal: what it adds or changes, its notes, its result). The
console shows the connection and what waits (with a key to open VS Code on it); the phone shows the counts and may
reject or send back, while approval stays in VS Code, where the changes can be seen whole (**Choice**).

## 10. Privacy, and how it is tested

- The secret is in `CLANK_HOME/secrets` only; no event, log or record holds it, or any Notion content.
- Notion content is for the local models (2026-10-17): the tools that build Clank never connect to anyone's real
  Notion. Clank is tested against a fake Notion (an `httpx2` mock serving a made-up workspace that follows
  Notion's API), and the first live check uses a test database of made-up entries that the owner creates and shares
  (the guide says how), never real ones.
- Images come only from the workspace's folder, and only an approved batch uploads them.

## 11. Phases

1. **The service and the agent:** the connection and its secret, reading, staging, applying, the agent's tools, the
   gateway's forwarding, `clank notion`: a batch can be staged by the agent and approved or rejected from the command
   line.
2. **Review in VS Code:** the view, the review editor (table, fields, page, preview), approving and rejecting entries
   and fields.
3. **Comments and sending back:** comments, revisions, `notion_reply`.
4. **The rest:** images (Notion's file uploads), tables in pages, the console and the phone.
