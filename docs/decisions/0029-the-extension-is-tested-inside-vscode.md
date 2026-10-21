# 0029. The extension is also tested inside a real VS Code, with @vscode/test-electron

- Status: Accepted
- Date: 2026-10-12
- Decided by: the owner asked that M0's deferred items be closed, this one among them ("complete the small issues
  that you left for later ... as well as everything else you have identified", 2026-10-12); the tool proposed by
  Claude in the follow-ups' plan; the owner can revisit it

## Context
Decision 0028 tested the extension's core without VS Code and left the glue (`src/extension.ts`: the status bar items,
the commands, the notifications) to M6, when `@vscode/test-electron` would come in. The glue is thin, but nothing
proves that VS Code activates the extension, that its manifest declares what its code registers, or that the status
bar shows what the controller says. M0.6's final review deferred exactly that.

## Decision
- **Tool.** `@vscode/test-electron` 3.1.0, a development dependency only (nothing of it is packaged). It downloads a
  VS Code build into `vscode/.vscode-test/` (not in the repository) and runs a suite inside it.
- **Version tested.** VS Code 1.138.0, the oldest the extension accepts (`engines.vscode`), so a newer API used by
  mistake fails the test.
- **Suite.** `vscode/host/`: the extension activates and registers its commands; with an empty CLANK_HOME its status
  bar says the service is not running; with a service (a small fake answering the API's routes) it shows the
  service's and Docker's state. The extension returns what its status bar shows from `activate`, for this suite.
- **Where it runs.** In continuous integration on Linux, under a virtual display (`xvfb-run`), in the job that runs
  for pull requests, version tags and on demand. On a working copy only when asked (`tools.extension --host`),
  because it opens a VS Code window; it uses a throwaway profile, never the user's.

## Alternatives considered
- **Wait for M6 (decision 0028).** The glue would stay untested through four milestones of use.
- **The installed VS Code's own `--extensionTestsPath`.** No dependency, but CI has no VS Code to run, and a working
  copy would test whatever version is installed.
- **@vscode/test-cli.** A runner around test-electron, with its own configuration file; test-electron alone is enough
  for one suite.

## Consequences
- The first host run downloads about 150 MB; later runs reuse it.
- `vscode/.vscode-test/` joins `vscode/.gitignore`.
- A change to the glue is tested in CI before a release.
