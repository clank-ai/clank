# 0028. The VS Code extension is TypeScript 7 tested with Node's runner; Clank's own tools write its types and package

- Status: Accepted
- Date: 2026-10-12
- Decided by: proposed by Claude in the M0.6 plan, under the owner's instruction to build M0 through the VS Code
  extension's shell (2026-10-11); the owner can revisit it

## Context
Design 0002 §2.16 puts the VS Code extension in `vscode/`, written in TypeScript, and decision 0015 leaves to this step
the choice of what generates the TypeScript types of Clank's kinds of record. The extension needs a compiler, types for
VS Code's and Node's APIs, a way to test it, a way to package it for `code --install-extension`, and a place in
continuous integration. Every dependency needs a reason (AGENTS.md).

## Decision
- **Language and compiler.** TypeScript 7.0 (its native compiler, `tsc`), strict, compiled to `vscode/out/`, with no
  bundler: the extension has no dependency at run time, only Node's and VS Code's APIs. Its types come from
  `@types/vscode` 1.138 (so it runs on VS Code 1.138 and newer) and `@types/node` 22 (the Node of VS Code's extension
  host).
- **Tests.** Node's own test runner (`node --test`) on the extension's core, which never imports `vscode`; what touches
  VS Code is a thin presenter the core drives, so the core is tested with a fake one. One test in the Python suite runs
  the extension's client against a real Clank service.
- **Types.** `tools/tstypes.py` writes `vscode/src/core/kinds.ts` from every kind's JSON Schema, the same schemas as
  `clank/schemas/`; `tools.check --fix` writes it again, and a test fails when it is out of date.
- **Package.** `tools/vsix.py` writes the `.vsix`: a zip of the extension's manifest, its content types and its files,
  which `code --install-extension` installs.
- **Continuous integration.** Node 22 from `actions/setup-node` v7.0.0, pinned to its commit; `tools.check` runs the
  extension's checks (`npm ci`, then compiling and testing it), so passing locally still means passing there.

## Alternatives considered
- **json-schema-to-typescript for the types.** More general, but a Node dependency for a file the Python tools write,
  and Clank's schemas use a small part of JSON Schema that a page of Python covers.
- **@vscode/vsce for the package.** The official packager, needed to publish to the Marketplace, but it brings about a
  hundred packages to zip a dozen files; it comes in if Clank is ever published there.
- **A bundler (esbuild, webpack).** Useful with run-time dependencies; the extension has none.
- **@vscode/test-electron.** Runs tests inside a real VS Code (a download of about 150 MB and a window); the presenter
  it would test is thin. It can come with M6, when the extension has views of its own.
- **ESLint.** The compiler's strict mode is the check for now.

## Consequences
- Developing Clank now needs Node 22 or newer and npm beside uv; `tools.check` says so when they are missing.
- The extension's files are in the repository; `vscode/out/`, `vscode/node_modules/` and `.vsix` files are not.
- Each new kind of record reaches the extension's types by regenerating, like its schema.
