# 0033. Clank needs nothing from the prototype, which is a template only

- Status: Accepted
- Date: 2026-10-13
- Decided by: the owner ("make sure that everything is self-contained ... we don't require anything from the prototype in
  order to use Clank, and that we are only using the prototype as a template and nothing more"; "Go ahead and delete this if
  we don't need it", of `clank import`)

## Context
The prototype, the owner's earlier suite, was Clank's template from the start (design 0001, PROTOTYPE.md), and M1 leaned
on it in a few places to get running quickly: the KVMem engine Clank runs is the build the prototype used (adopted where it
is, design 0003 §7.1), with the model files the prototype downloaded; the vision projector's revision is unknown, so Clank
could not download it; `clank import` turned the prototype's profiles into presets; the engines' port and, briefly,
NInfer's model name followed what the prototype's tools ask for; and some of Clank's own descriptions named the prototype.

## Decision
- Nothing Clank does at run time needs the prototype: no file, program, container, setting or name of the prototype's. An engine
  Clank runs is one Clank installed by its own recipe (or one the user adopts, as any user may adopt their own build);
  every model file it uses is in its catalog with a source Clank can download and a checksum it verifies.
- `clank import` is removed (its route, its command, its tests and its recorded registry). The presets it wrote
  on the owner's machine are the owner's presets and stay until the owner removes them.
- The prototype remains a template: what was learned from it stays recorded in PROTOTYPE.md and in the designs that cite
  it, and a default may still come from what was measured there (said so where it is set).
- Coexistence is not dependence: Clank still tells the containers of other programs apart (the prototype's among them) so it
  never stops one without asking, and it still checks whether a port it wants is held by another program.

## Alternatives considered
- **Keep the importer as a one-time migration tool.** It had done its work (the owner's seven profiles were imported),
  and it was the last feature that read anything of the prototype's.
- **Keep the adopted KVMem build.** It works, but it is the prototype's checkout, with local changes, and a second machine
  could not have it.

## Consequences
- KVMem gets a recipe (clone the release, apply KVMem's own patches, build with CUDA in an environment of its own, as
  decision 0032 says) and its model files are downloaded by Clank, the projector from a source whose revision is known.
- The engines' port keeps its default (18200) for its own sake; its description no longer mentions the prototype.
- Design 0003 §7.4 and design 0001 §9.2-§9.3's importer rows are marked removed.
