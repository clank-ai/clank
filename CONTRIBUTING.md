# Contributing to Clank

Thank you for helping. Clank is built in small, recorded steps; a contribution follows the same rules.

1. **Read [AGENTS.md](AGENTS.md) first.** It says where things are, how work is recorded (decisions, designs, plans)
   and the rules every change follows. It is written for people and for language models alike.
2. **Tests come first.** Write the failing test, then the code. Test names are sentences, and each test file's
   docstring names the design sections it verifies.
3. **Run the checks.** `uv sync`, then `uv run python -m tools.check --fix` (it formats, regenerates the generated
   files and runs every check continuous integration runs). Everything must pass. The VS Code extension needs Node 22
   or newer.
4. **American English** everywhere: code, comments, documents, messages, the console.
5. **Nothing personal or secret.** No API keys or tokens, no names of people or machines, no home folders or private
   paths, no one's private research or projects: use made-up examples (`myproject`, `C:\work\myproject`).
6. **No new dependency** without a decision record that says why it is worth it.
7. **Small commits** whose messages say what changed and why. A change that makes a document wrong updates it in the
   same commit.

To report a security problem, see [SECURITY.md](SECURITY.md) instead of opening an issue.

By contributing, you agree that your contribution is released under the [GNU Affero General Public License, version 3](LICENSE) (AGPL-3.0-only), like the rest of Clank.
