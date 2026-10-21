# The loop guard: implementation plan

> At the owner's request (2026-10-18): "I also want you to go ahead and implement the loop guard in the gateway." As
> for the plan mode's plans, the files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** design 0004 §2, *a loop guard*: the gateway stops a streamed answer that repeats itself, soon, and says so;
never an ordinary one.

**Spec:** [design 0004](../design/0004-working-in-a-folder.md) §2; [decision 0040](../decisions/0040-the-gateway-stops-an-answer-that-repeats-itself.md);
[the measurement](../measurements/2026-10-18-repetition-in-answers.md).

## Global Constraints

- The tests never read the owner's records: real answers are represented by Clank's own files and by text written for
  the tests; the loops by the shapes measured (closing tags again and again, `0.0 ` again and again, prose said again).
- Standard library only (`zlib`); the guard is pure (no I/O), and reads each part every 128 characters (one
  compression per stretch the part is long enough for).
- The owner is the sole author of every commit; American English; tests named as sentences.

## Tasks

- [x] **The guard:** `LoopGuard(windows, ratio, tool_windows)`, `feed(part, text, name="")` returns what repeated, in
  words, the first time a part's newest stretch compresses under the ratio (then `tripped` holds it, and `brief` the
  same without numbers); the parts are `thinking`, `answer` and `tool <index>`, a tool call read over its own stretches
  (`clank/components/gateway/loops.py`; `tests/components/gateway/test_loops.py`: closing tags found within the short
  stretch, `0.0 ` too, prose said again found by the long stretch only, files written from a template by a tool call
  never, Clank's code, documents and its most repetitive file never, each tool call read apart, the share and the
  stretches are its settings, the words say which part and which stretch, the brief words carry no numbers).
- [x] **Its settings:** `loop_guard` (on), `loop_windows` (2,000 and 8,000), `loop_tool_windows` (2,000), `loop_ratio`
  (0.06) on `GatewaySettings`; the schema regenerated. Each settings kind now says whose start applies a change
  (`NEXT_START`, `applies` in `GET /kinds`; the gateway's: `clank gateway restart`; a preset's: its slot's), and the
  Records page shows it (`tests/kernel/test_api.py`).
- [x] **The gateway uses it:** each streamed event's thinking, text and tool-call arguments fed to the request's guard,
  each call by its index; when it trips, the stream ends with an error event (`model_looped`) whose words say what
  repeated and how to let such an answer through, without numbers, and the connection to the engine is closed; the
  record keeps `looped` and `error` (`tests/components/gateway/test_server.py`, with the fake engine's
  `--fake-loop-after` and `--fake-loop-in`: a looping answer, thinking and tool call are stopped and the engine stops
  writing; two calls are read apart; the settings' stretches are used; with the guard off it runs to its end). Found on
  the way and fixed: after a resent answer, a client that left was not kept as having left.
- [x] **What the console shows:** a record in brief says `looped`; the Requests page marks it
  (`tests/components/gateway/test_recent_requests.py`, `tests/console/test_requests_page.py`).
- [x] **Documents:** design 0004 §2 (*built*), decision 0040, the measurement, the glossary, this plan; the generated
  files regenerated.

## Review

A review of the change in four directions (the stream, the detector, the client, the tests and documents), each
finding checked by a second reader trying to refute it, confirmed twelve findings; all are answered above: tool calls
read over the short stretch only (templated files), the reach on prose stated as it is, the thinking path and per-call
reading and the settings proven through the gateway, the words to the agent without numbers and with the way to turn
the guard off, when a gateway setting applies, the resent answer's `left`, and the documents' figures.
