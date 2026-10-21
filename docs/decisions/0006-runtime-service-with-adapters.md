# 0006. One runtime service with an adapter per engine

- Status: Accepted. Refined by [0013](0013-one-service-control-and-data-planes.md): the runtime service is now the
  runtime component of one Clank service
- Date: 2026-10-11
- Decided by: the owner's answer to "Which structure should the runtime layer have?" (chose "A: runtime service")

## Context
The user must be able to choose the model, how it is served (KVMem/llama.cpp, NInfer, KVMem with NInfer, and others
later), the context window and every other option, and switch between them, from the console and from other front
ends. In the prototype this knowledge is spread over a registry, a shell script, the monitor and the menu.

## Decision
One long-running runtime service owns: which provider serves which slot, the launch options in effect, the role
sampling, switching (validate, check the fit in memory, check what is busy, stop, start, check health, and go back to
the last configuration that worked if the new one fails), health, metrics and history. Every engine is one adapter
module with a fixed interface (its options as a typed list, how to launch it on its host, health, metrics, stop).
The console, menus, the editor integration and other programs are clients of the service's one HTTP API.

## Alternatives considered
- **The console manages the model itself.** Fastest to a working console, but closing the console must not stop the
  model, and every other front end would need its own copy of the logic.
- **A settings file plus a reconciler (`apply`).** Transparent and versionable, but live state still needs a service;
  its best property is kept by decision [0007](0007-settings-in-readable-files.md).

## Consequences
- The service is the single source of truth; front ends hold no state of their own.
- Adding an engine means writing one adapter and its tests.
- The service must stay up while a model runs, independent of any front end.
