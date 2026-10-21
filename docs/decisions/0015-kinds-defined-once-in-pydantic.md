# 0015. Each kind of record is defined once, in Pydantic; its schemas and types are generated from that definition

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
A kind of record (a preset, a workspace, a mode, a question) appears in many places: the file the user edits, the API,
the console's forms, the VS Code extension and the phone page (both TypeScript), and the documentation. Written by
hand in each place, the copies drift apart, and a mismatch shows up as a bug in whichever client was not updated.

## Decision
Each kind is one Pydantic class in its component's `kinds.py`, every field with its type, label, help and default.
From that one definition Clank generates the JSON Schema of the kind's files (`clank/schemas/`), the API's description
(OpenAPI), and the TypeScript types the extension and the phone page use. A test fails when a generated file is out of
date. The explain key (design 0001 §5.4) shows each field's label and help.

## Alternatives considered
- **JSON Schemas written by hand, next to the code.** Two sources of truth for every kind.
- **Standard dataclasses with a separate validator.** More code for what Pydantic does, and FastAPI (decision
  [0016](0016-fastapi-and-uvicorn.md)) is built on Pydantic.
- **attrs or msgspec.** Faster or lighter, but less known to people and to models (principle 4), and not what FastAPI
  uses.

## Consequences
- Pydantic (version 2) is a runtime dependency.
- Adding a field is one line in one class, then regenerating; a field whose meaning changes needs a migration (design
  0001 §7.7).
- The generator of TypeScript types is chosen when the VS Code extension is built (M0.6).
