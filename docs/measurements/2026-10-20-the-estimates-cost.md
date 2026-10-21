# The cost of the context's estimate (2026-10-20)

**When:** 2026-10-20, on this machine's CPU (32 threads) while other work ran, with Python 3.12 from
the repository's environment. Synthetic requests only: no model, engine, GPU, OpenCode or record of the owner's was
used. This is the measurement design 0012 §10 lists before step 12, "the estimate's CPU cost on a 262,144-token
request" ([plan s22](../plans/s22-monitor-the-parts-and-the-context-view.md), task 7).

**Question:** what does the gateway's census of a request (`clank/components/gateway/census.py`: each part's
characters, each item, loop text by the loop guard's measure) cost on the largest request the daily preset takes, and
the service's estimate made from it (`clank/components/agents/estimate.py`)?

## The requests

A request in OpenCode's shape, built by a script with a fixed seed: a system prompt of 11,000 characters, twelve tool
definitions of 300 to 9,000 characters, the owner's message, then steps until the body holds about 262,144 tokens at
3.3 characters a token. Each step is one answer (a thinking, one call) and the call's result: half reads of code
(800 to 9,000 characters back), a third commands (100 to 3,000 characters of output), the rest file edits and writes
(writes of 2,000 to 12,000 characters, which the census measures as the model's own text). Code is lines of a small
Python-like vocabulary, prose words in no order; both compress as ordinary text does, so no item is taken for a loop.

- **Mixed**: thinking of 200 to 6,000 characters a step; 113 steps, 906,299 bytes of JSON, 864,394 characters counted
  (about 261,900 tokens); 88 items long enough to measure (2,000 characters or more).
- **Short thinking**: thinking of 200 to 1,500 characters and no writes; 185 steps, 922,465 bytes, 857,830 characters;
  no item long enough to measure.
- **The worst case**: every item the model's own (200 answers of 2,000 characters of text and 2,300 of thinking, 860,008
  characters), so all of it is compressed.

Each was timed seven times (five for the worst case); the medians and the least are given.

## What it costs

| Request | `json.loads` of the body | The census | Of it, zlib | The estimate |
| --- | --- | --- | --- | --- |
| Short thinking | 0.9 ms | 2.3 ms | 0 ms | 0.1 ms |
| Mixed | 0.7 ms | 8.1 ms | 5.0 ms | 0.1 ms |
| The worst case of those | | 19.1 ms | most of it | |
| A chat of 3,000 answers without calls (838,674 characters) | | 15.3 ms | 0 ms | |
| One `write` call of 860,000 characters (code; prose) | | 15.4 ms; 26.2 ms | most of it | |

**Corrected after the review** (the same day): the first three requests did not cover two shapes. A chat of answers
without calls cost about 250 ms (the review's machine, 3,000 answers): each such item looked through every answer for
the calls around it, so the census grew with the square of the chat's length; it is now one pass and a binary search
for each item (`census._around`), 15.3 ms here for 3,000 answers, and a test holds 10,000 under a second. And one
item that holds most of the request, a `write` of 860,000 characters measured as the model's own text, took 39 ms on
the review's machine, 26.2 ms here: "under 20 ms at worst" was wrong. The worst seen is about 40 ms.

The census keeps 52 to 63 items, 13 to 16 KB as JSON: the biggest 40 and each part's 8. The rest of its time is one
pass over the messages, a `json.loads` of each call's arguments (to say what it does) and the words of each item.

## What it means

- **Once per request, off the event loop**: the gateway makes the census in a worker thread once a request's body is
  read (`server.py`, `counted`), so a request waits at most the census's time (about 8 ms, about 40 ms at the worst
  seen) before it goes on, against seconds of the engine's reading of a 262,144-token prompt; streams of other requests in flight
  are not held up meanwhile.
- **The estimate is nothing to speak of**: the service makes it from the census each time the Monitor reads the totals
  (once a second while the page is on screen); 0.1 ms.
- **No change is needed**: design 0012 §2's fallbacks (fewer redraws, frozen panels) are for the console's drawing, and
  nothing here draws.

## Not measured here

- The census against the engine's own count of each part (the estimate's error): it needs an engine that counts each
  part (llama.cpp's `/tokenize`, or the KVMem patch of design 0012 §4.4); owed to the owner (§10, before step 13).
- The chat template inside the model file, and whether its markers are single tokens (§10, before step 12): it needs
  the model file read on the owner's machine; owed to the owner.
