# 0022. Development tools: uv, hatchling, pytest, Ruff and mypy

- Status: Accepted; its snapshot tool is superseded by [0027](0027-console-snapshots-are-text.md)
- Date: 2026-10-11
- Decided by: proposed by Claude in the M0.1 plan, under the owner's instruction to "plan M0.1, and start building"
  (2026-10-11); the owner can revisit it

## Context
Design 0001 §7.1 asks for Python 3.12 or newer, in Clank's own environment, with every dependency pinned in a lock
file; §8.4 asks for tests, a lint and a type check on every push, and leaves the tools (the test runner, the linter,
the type checker, Textual's snapshot plugin) to a decision record written with the first implementation plan. Clank
runs on Windows (its clients) and in WSL or Linux (its service), so one lock must hold on both.

## Decision
| Need | Tool | Notes |
| --- | --- | --- |
| Environments, Python versions, the lock, running commands | uv | `uv.lock` pins every dependency for every platform; `.python-version` asks for 3.12, the oldest Python Clank supports |
| Building the package | hatchling | The version is read from `clank/__init__.py` |
| Tests | pytest | Asynchronous tests use AnyIO's pytest plugin, which comes with FastAPI's dependencies (from M0.2) |
| Lint and formatting | Ruff | One tool for both; lines of 120 characters |
| Types | mypy, strict | Pydantic's plugin is added with Pydantic (M0.2) |
| Snapshots of the console | pytest-textual-snapshot | Superseded by decision 0027: text snapshots made by the console itself |

Each tool enters the lock when it is first used.

## Alternatives considered
- **pip with venv and pip-tools.** Standard, but slower, with no management of Python versions, and a lock that holds
  for one platform unless one is kept per platform.
- **Poetry or PDM.** Complete, but heavier, with conventions of their own; uv also installs Python itself.
- **setuptools.** Familiar, but it needs more configuration for the same result here.
- **Black, Flake8 and isort.** Three tools where Ruff is one, and slower.
- **Pyright.** What VS Code's Pylance uses, so its findings match the editor's, but it runs on Node.js; mypy is pure
  Python and has Pydantic's plugin.
- **pytest-asyncio.** One more dependency, where AnyIO's plugin comes with FastAPI.

## Consequences
- One command prepares a working copy (`uv sync`), and every command runs through `uv run` (AGENTS.md, Commands).
- Continuous integration installs from the same lock and fails when `pyproject.toml` and `uv.lock` disagree
  (`uv sync --locked`).
- Development uses Python 3.12, so nothing newer slips in; continuous integration also runs Python 3.14, on Linux and
  Windows, for pull requests and releases.
