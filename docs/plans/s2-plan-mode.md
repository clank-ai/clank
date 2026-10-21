# Plan mode, phase 1: implementation plan

> At the owner's request (2026-10-15): "write the phase 1 plan and begin implementing immediately. Once this passes all
> our tests, go ahead and push to GitHub." As for M1 and M8.0, this plan gives the files, interfaces and tests by name
> and intent; the code is in the commits, written test-first. Tasks 5-9 were done in the owner's own project
> repositories, outside Clank, and are only summarized here.

**Goal:** design 0009 §1-§6: Clank's planner in OpenCode (Tab: Build ↔ Planner), its rules, the plan's format and its
template, `/implement`, plan files accepted in review mode, MCP checks that keep read-only marks, and, outside
Clank, a simulator's measured cost (thread counts in the estimate, a benchmark, the result's layout, the storage of a
saved run).

**Spec:** [design 0009](../design/0009-plan-mode.md) §1-§6 and §9; [decision 0038](../decisions/0038-plan-mode-is-an-opencode-agent.md);
design 0007 §3 (review and auto); design 0004 §10 (MCP servers given to the agent).

## Global Constraints

- OpenCode 1.19.0, as measured (design 0009 §2): rules are flattened in order and the last match wins; the agent's
  `permission` in the configuration comes last; `*` in a pattern matches any characters, `/` included; a pattern ending
  in ` *` also matches the bare command; an MCP tool is named `sanitize(server) + "_" + sanitize(tool)` with
  `sanitize = replace [^a-zA-Z0-9_-] by _`; a tool denied for an agent is not shown to it.
- The planner may write Markdown (`*.md`) and nothing else; its reading commands are exactly design 0009 §3's list;
  MCP tools are allowed only when the server's last check marks them `readOnlyHint`.
- Every agent keeps Clank's top-level `permission` (`external_directory`, `webfetch`, `websearch` denied, `edit: ask`).
- A plan is a file whose front matter (between a first line `---` and the next `---`) has `kind: plan`.
- The owner is the sole author of every commit: no co-author lines, no "generated with" lines.
- American English; tests first; test names are sentences; each test file's docstring names the design sections
  (AGENTS.md).

## Review Focus

1. **A server never checked, or checked before marks were kept:** the planner gets none of its tools (`<server>_*`
   denied), and its instructions tell the owner to check it (`clank mcp check NAME`). Pinned in Task 3.
2. **A server or tool name with characters OpenCode replaces** (`my.server`): the rules name the tool as OpenCode
   does. Pinned in Task 3.
3. **A Markdown file that only mentions `kind: plan`** (in its body, in a malformed header, with Windows line endings):
   only a real header makes a plan. Pinned in Task 2.
4. **The implementer creating a plan, or an edit that drops the header:** "before or after" decides; both are accepted
   in review mode. Pinned in Task 2.
5. **A benchmark asked for more threads than the machine gives, or for fewer samples than threads:** the result
   says which figures are measured and which projected, counts busy threads only, and writes nothing (outside Clank,
   tasks 5-9).

## Files

| File | What changes |
| --- | --- |
| `clank/components/tools/mcp.py` | `Tool.read_only` from the tool's `annotations.readOnlyHint` |
| `clank/components/tools/service.py` | a check keeps `read_only` per tool |
| `clank/components/agents/plans.py` (new) | `is_plan(text)`: whether a file's front matter says `kind: plan` |
| `clank/components/agents/review.py` | an edit to a plan is accepted at once in review mode, as "Clank (a plan's progress)" |
| `clank/components/agents/prompts/planner.md`, `implement.md` (new) | the planner's instructions (design 0009 §3.1, §4) and `/implement`'s (§5.1) |
| `clank/components/agents/adapters/opencode.py` | the `planner` agent (OpenCode's `plan` disabled), its rules, the `implement` command |
| `clank/components/agents/adapters/program.py` | `configuration` takes the read-only tools of each server |
| `clank/components/agents/service.py` | `_read_only(workspace)`: each given server's read-only tools from its last check |
| `docs/studies.md`, `docs/design/0009-plan-mode.md`, `docs/ROADMAP.md`, generated pages | plan mode for the owner; statuses |
| The owner's own simulator and study repositories (outside Clank) | Tasks 5-9 |

## Tasks

### Task 1: MCP checks keep each tool's read-only mark

- [x] Test (`tests/components/tools/test_mcp.py`): a server whose `tools/list` gives one tool with
  `annotations: {"readOnlyHint": true}`, one with `false` and one without annotations is checked as
  `read_only` True, False, False.
- [x] Test (`tests/components/tools/test_servers.py`): the remembered check (`Tools.checked`) holds `read_only` for each
  tool.
- [x] `Tool` gains `read_only: bool = False`; `_checked` reads `tool.get("annotations", {}).get("readOnlyHint") is
  True`; `_check`'s result adds `"read_only"` per tool. Commit.

### Task 2: plans are recognized, and review mode accepts an edit to one

- [x] Test (`tests/components/agents/test_plans.py`, design 0009 §4, §5): `is_plan` is true for `---\nkind: plan\n---`,
  with `status:` and `title:` lines, with `\r\n` line endings, with spaces around the value; false for `None`, `""`, a
  body line `kind: plan` without a header, a header that never closes, `kind: plans`, `kind: plan` in a second
  `---` block.
- [x] Test (`tests/components/agents/test_review.py`): in review mode an ask to edit `plan.md` whose current text has the
  header is answered `once` at once, with no question, `by` "Clank (a plan's progress)", the change's `mode` "auto" and
  `plan` True; the same for a new file whose proposed text has the header, and for an edit that removes it; an ask to
  edit `a.py` still waits for the owner.
- [x] `plans.is_plan(text: str | None) -> bool`; in `Review._change`, `plan = is_plan(before) or is_plan(after)`, and
  `mode = "auto" if plan else self.mode(workspace)`; `_asked` answers a plan's change with `PLAN = Actor(kind="clank",
  via="a plan's progress")`; the module docstring says so. Commit.

### Task 3: the planner and `/implement` in OpenCode's configuration

- [x] Test (`tests/components/agents/test_opencode.py`, design 0009 §3, §5): the configuration has `agent.plan ==
  {"disable": true}` and `agent.planner` with `mode` "primary", a `description`, the prompt of `planner.md`, and
  `permission` in this order: `edit` `{"*": "deny", "*.md": "allow"}`; `bash` `{"*": "ask"}` then each reading command
  as `"<command> *": "allow"` (design 0009 §3's list; `git status *`, `git log *`, `git diff *`, `git show *`);
  `question` "allow"; `task` `{"*": "deny", "explore": "allow"}`; for each server, `"<server>_*": "deny"` then
  `"<server>_<tool>": "allow"` for each read-only tool, names sanitized as OpenCode does (`my.server` →
  `my_server_*`); the top-level `permission` unchanged. `command.implement` has `agent` "build", a `description`,
  and a template that is `implement.md` with `$ARGUMENTS` for the plan's path.
- [x] Test: the prompts say what design 0009 §3.1, §4, §4.1-§4.3 and §5.1 require (each section of the default
  layout named, Deliverables last; "never write code"; the benchmark; the owner's limits; `clank mcp check`).
- [x] Test (`tests/components/agents/test_agent_servers.py`): `prepare` writes the read-only tools of each given server
  from its last check into the planner's rules; a server never checked gets only its deny rule.
- [x] `AgentProgram.configuration(model, servers, read_only: Mapping[str, Sequence[str]] | None = None)`;
  `OpenCode.configuration` adds `agent` and `command`; the prompts are read with `importlib.resources`;
  `Agents._read_only(workspace)` uses `Tools.checked(name, scope, folder)`; `prepare` and `configure` pass it. The
  adapter's docstring says so. Commit.

### Task 4: documents and checks

- [x] `docs/studies.md`: plan mode (Tab, what the planner may do, `/new` then `/implement`, checking a server again for
  its read-only marks). Design 0009: §1-§6 "built 2026-10-15 (phase 1)"; its index row; decision 0038 stays proposed;
  `docs/ROADMAP.md` M5 line; this plan's index row. `uv run python -m tools.check --fix`; every check passes. Commit;
  push `main`.

### Tasks 5-9: outside Clank

- [x] In the owner's own simulator, test-first, on a branch merged only when the owner said so: the estimate takes
  thread counts and gives the saved result's layout; a read-only benchmark (design 0009 §6) that measures a sample on
  one thread and on the most threads the machine gives, projects the rest and writes nothing; the storage of a saved
  run; its documents.
- [x] In the owner's study repository: a plan template (design 0009 §4-§4.3) named in its `AGENTS.md`; the workspace
  set up and its MCP server checked, so its read-only marks are kept.

### Task 10: in the real container

- [x] `prepare` the workspace; `opencode serve` on the written configuration: `GET /agent` shows `planner` with its
  rules and no `plan`; `GET /experimental/tool` for the planner lists the read-only tools of the project's server and
  not the run tools. A session with the planner asked to write a two-line plan writes it, and is refused a `.py` file.
