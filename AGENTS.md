# Working on Clank (for people and for language models)

Read this file first. It says where things are, how work is recorded, and the rules every change follows. It is
written for a person who knows programming but not this project, and for a language model (including a small local
one) that is asked to understand or improve Clank. Keep it true: a change that makes it wrong updates it in the same
commit.

## Read order

1. [docs/PRINCIPLES.md](docs/PRINCIPLES.md): why Clank exists and the rules it follows.
2. [docs/ROADMAP.md](docs/ROADMAP.md): what is being built now, and what comes next.
3. The design document of the part you work on ([docs/design/](docs/design/README.md)) and the decisions it cites
   ([docs/decisions/](docs/decisions/README.md)).
4. [docs/GLOSSARY.md](docs/GLOSSARY.md) whenever a word seems to have a special meaning: it does, and it is defined
   there.
5. [docs/CODEMAP.md](docs/CODEMAP.md) (one line per module: what it is for) and [docs/TESTS.md](docs/TESTS.md)
   (which tests hold each design section to its word), both generated. Every module begins with a docstring saying
   what it does and why it is built that way.

## Layout

| Path | What |
| --- | --- |
| `README.md` | What Clank is, its status, where to read next |
| `AGENTS.md` | This file |
| `LICENSE`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md` | The GNU Affero General Public License, version 3 (AGPL-3.0-only); what each release brought; how to report a security problem and what Clank guards; how to contribute |
| `clank/` | The `clank` package: the kernel (`clank/kernel/`: records, settings files, the state database, events, operations, questions, access, adapters, running programs, the API, the service), the components (`clank/components/`: `machine`, `workspaces`, `runtime`, `gateway`, `tools`, `agents`, `remote`, `notion` and `flows` so far, each in the same shape; a component's kinds of adapter in its `adapters/`, its console pages in its `console/`), the console (`clank/console/`: the shell, the shared pages, `clank.tcss`), the `clank` command (`clank/cli/`), the API client the commands share (`clank/client.py`), how amounts of money and tokens are written for the service and every client (`clank/money.py`), everything declared in one place (`clank/registry.py`), the generated settings schemas (`clank/schemas/`); each milestone adds its parts (design 0002 §2.16) |
| `tests/` | The tests (pytest), by part: `tests/kernel/`, `tests/components/`, `tests/cli/`, `tests/tools/`; `tests/contract/` runs one contract per kind of adapter against what the real programs answered, recorded in `tests/fixtures/` (its README says how); `tests/fakes/` holds what tests use in place of real programs; `tests/console/` drives the console headless against a service served in the test, and compares its frames with the text snapshots in `tests/console/snapshots/` (`CLANK_UPDATE_SNAPSHOTS=1` rewrites them; read the difference before committing); `tests/test_repository.py` runs the repository's own checks |
| `vscode/` | The VS Code extension (TypeScript, decision 0028): `src/core/` is its logic, tested by Node's own runner without VS Code; `src/extension.ts` is the thin glue; `src/core/kinds.ts` is generated; its README says what it shows |
| `tools/` | Development tools, never shipped: the generated files (code map, tests page, events page, settings schemas), the documentation, secrets, spelling and colors checks, and `check`, which runs every check |
| `pyproject.toml`, `uv.lock`, `.python-version` | The package, its dependencies (pinned in the lock) and its tools' settings; Python 3.12 for development |
| `.github/workflows/checks.yml` | Continuous integration: the same checks, on every push |
| `docs/PRINCIPLES.md` | The design philosophy |
| `docs/ROADMAP.md` | The milestones in build order and the parts they build, with their status |
| `docs/GLOSSARY.md` | Terms, defined once |
| `docs/CODEMAP.md`, `docs/TESTS.md`, `docs/EVENTS.md`, `docs/API.md` | Generated: one line per module; the tests of each design section; every event type; every route of the API |
| `docs/PROTOTYPE.md` | The earlier private prototype Clank began from, and the lessons measured there |
| `docs/decisions/` | Decision records, numbered, never edited away |
| `docs/design/` | Design documents, sections with review status |
| `docs/plans/` | Implementation plans, one per milestone step, with their progress |
| `docs/research/` | Surveys of what others built, each with what Clank takes from it now and what is kept for later design choices (orchestration first) |
| `docs/models/` | One page per model setup worth building again ("frontier 262K" first): its files, its engine, every setting and why, and how to set it up on a new machine |

## Commands

From the repository's root. Clank's environment is managed by [uv](https://docs.astral.sh/uv/) (decision 0022).

```
uv sync                                # set up the working copy: Python 3.12 and every dependency, from uv.lock
                                       # (the VS Code extension also needs Node 22 or newer; tools.check installs its tools)
uv run clank --version                 # the clank command, from the working copy
uv run clank doctor                    # check this computer (works without the service; changes nothing)
uv run clank serve                     # run the Clank service here (--background to detach); clank stop ends it
uv run clank status                    # whether it runs, and what waits for you
uv run clank events --follow           # what happens, as it happens; also: clank questions, operations, records
uv run clank docker status             # Docker's state and whose each container is; also: clank docker start, stop
uv run clank console                   # the console (starts the service in the background if need be); F1 for keys
uv run clank console --snapshot        # one frame of the console as text, for scripts, reports and models
uv run python -m tools.vsix            # package the VS Code extension (after tools.check compiled it), then:
code --install-extension vscode/clank-0.9.2.vsix   # install it in VS Code (the name tools.vsix printed)
uv run python -m tools.check           # every check continuous integration runs: formatting, lint, types, tests
uv run python -m tools.check --fix     # first fix what can be fixed, and regenerate every generated file
uv run python -m tools.extension --host  # the extension's suite inside a real VS Code (opens a window)
uv run pytest tests/test_version.py    # one test file
```

## How work is recorded

- **A decision** (a choice between alternatives that someone will later ask "why?" about) gets a decision record:
  `docs/decisions/NNNN-short-title.md` with the next number, written from the template in
  [docs/decisions/README.md](docs/decisions/README.md), and a line in that file's index. A decision is never deleted or
  rewritten: a later decision supersedes it, and both say so.
- **A design document** has numbered sections. Each section has a status: *proposed*, *approved* (with the date), or
  *revised after approval* (with what changed and why). Only approved sections are built. The index in
  [docs/design/README.md](docs/design/README.md) shows every document and its sections' status.
- **A plan** is written for each milestone step before its code ([docs/plans/](docs/plans/README.md)): small tasks,
  each starting with a failing test; its checkboxes are ticked as the work is done.
- **The roadmap** lists every milestone and part with its status and is updated in the same commit as the work it
  describes.
- **Each step is a small commit** whose message says what changed and why, pushed to GitHub (`origin`, branch `main`).

## Rules for every change

- **Plain language, small pieces.** One subject per file, short files, links instead of repetition. A reader with a
  small context window must be able to load just what it needs.
- **Transparency.** Everything Clank does must be visible and explainable to its user: what runs, with which settings,
  what it costs, and why. A setting the user cannot see or change is a bug. Settings live in readable files.
- **Nothing personal or secret in the repository:** no API keys or tokens, user names, home directories, machine
  identifiers (GPU UUIDs, host names) or private paths. Machine-specific settings live in the local configuration,
  outside version control (`.gitignore` lists where).
- **American English** in everything: code, comments, documents, messages, the console.
- **No new dependency** without a decision record that says why it is worth it.
- **Tests come first** (design 0001 §8.6). Each test file begins with a docstring naming the design sections it
  verifies, written "Design 0002 §3.2" (several of one design as a list, "Design 0011 §4, §8 and §11": a range counts
  for its first section only), and test names are sentences (§8.5). `docs/TESTS.md` lists each section with the files
  that name it. Generated documents are regenerated in the same commit (`uv run python -m tools.check --fix`).
