# Clank's principles

These are the rules every part of Clank follows. A design or a change that breaks one of them must say so and why, in
a decision record. Decided by the owner on 2026-10-11 ([decision 0002](decisions/0002-design-principles.md)).

1. **Replace hosted assistants.** Clank is a complete suite (a coding agent, research tools, model management,
   monitoring) that lets its user stop depending on products like Codex. A feature is judged by whether it moves
   Clank toward that.

2. **Modular, plug and play.** Every piece (the model, the engine that serves it, the provider, sampling, tools,
   views) can be swapped behind a small documented interface. A model, or a way of serving one (a serving setup: an
   engine, how it is built, and its validated launch profile), is added by adding one adapter or one catalog entry;
   nothing else changes. No part depends on another part's internals. *(Sharpened 2026-10-11 by the owner, decision
   [0010](decisions/0010-serving-setups-are-plug-and-play.md).)*

3. **Radical transparency.** The user can see everything Clank does and why: which model and engine run, with which
   settings, every request and what it cost. And the user can change any of it, from technical settings to small
   things like the layout of a panel, without reading through code to find where it is hidden. Settings live in
   readable files; every choice Clank makes on the user's behalf is shown and can be overridden.

4. **Readable and changeable by people and by models.** Clank is organized so that its user's own local model can
   understand the architecture and improve Clank under the user's direction: small modules that each begin by saying
   what they do and why, one subject per file, a code map, decision records, and tests that say what they prove.

5. **Portable.** Clank works with any local model and engine the hardware can run, with an API key for a hosted
   model, or with a model on another machine (an HPC cluster, a server on the network), and a built-in guide sets each
   one up. The machine it was first built on (one 16 GB GPU, Windows with WSL2) is an example, never an assumption.

6. **The computer stays usable.** Clank shares the machine with its user: no frozen desktop, no endless redraws
   (they take GPU time from the model), no surprise downloads or background load the user did not ask for.

7. **Engineered as a product.** Design before code, every decision recorded, a test for every behavior, small
   reviewed steps pushed to GitHub, releases with notes. What is not tested does not work.
