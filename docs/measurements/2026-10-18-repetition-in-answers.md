# Repetition in the model's answers

**When:** 2026-10-18, the owner present; read from the gateway's records of 2026-10-14 to 2026-10-18 (every request
OpenCode made through Clank), by a script that printed numbers only, never what was asked or answered.

**Question:** how can the gateway tell an answer that repeats itself from an ordinary one, soon enough to stop it, and
never stop ordinary work?

## What happened

At 12:04 the agent's model (Qwen3.8-27B on KVMem, `daily 262K`) began a `bash` call, wrote about 200 characters of
its command, then repeated closing tags (`</f>`, `</invoke>`, `</functions>`) until the answer's limit: 16,384 tokens
in 3.7 minutes. The tool-call format ends an argument only with `</parameter>` on its own line (the engine's grammar,
`llama.cpp/common/chat.cpp`), so every tag it tried was more of the command. OpenCode could not read the cut call and
kept it, with its error repeating it, in the session: about 23,000 tokens, sent again with every later step. The same
happened at 00:54 (another `bash` call), and on 2026-10-15 a thinking ended in `0.0 0.0 0.0 …` until its budget. Three
loops in about 710 agent requests; sampling had no penalty against repeating (presence 0, repetition 1).

## The measure

The share a stretch of text compresses to with zlib (level 6): a repeat of a few lines compresses to almost nothing;
code, prose and data keep most of their size. Read on the newest 2,000 and 8,000 characters of each part of an answer
(its thinking, its text, each tool call's arguments), as it streams, every 64 characters.

## Ordinary answers

1,566 distinct outputs (thinking, text and tool-call arguments, 1.46 million characters; the two `bash` loops are
not among them, OpenCode kept them apart), the thinking loop of 2026-10-15 left out:

| Window | Outputs that long | Lowest | 1% | 5% | Median |
| --- | --- | --- | --- | --- | --- |
| 2,000 characters | 172 | 0.188 | 0.234 | 0.316 | 0.443 |
| 8,000 characters | 52 | 0.261 | 0.261 | 0.324 | 0.385 |

Clank's own files, read the same way: the most repetitive is a recorded engine log
(`tests/fixtures/kvmem-llamacpp/v0.16.0-rc1/program.json`, 0.097 and 0.108); then the llama.cpp log (0.178), then
code and documents (0.22 and up). Text written to look repetitive: sixty similar test functions 0.145; a list of 900
zeros (`[0.0, 0.0, …]`, some 4,500 characters) 0.015 (it would be stopped, as it should be: no model writes that on
purpose).

## The loops

Characters of the call's text (the repeat begins about 200 characters in) before the 2,000-character window falls
under each share:

| Loop | 0.03 | 0.05 | 0.06 | 0.08 | 0.10 |
| --- | --- | --- | --- | --- | --- |
| 12:04, `bash` (32,504 characters) | 3,088 | 2,256 | 2,192 | 2,192 | 2,064 |
| 00:54, `bash` (50,167 characters) | 2,192 | 2,128 | 2,128 | 2,064 | 2,000 |

The thinking of 2026-10-15 (4,459 characters) came under 0.10 at 2,320 characters and settled at 0.013.

Read as the gateway reads (every 128 characters, both stretches), the two `bash` loops come under 0.06 at 2,176
characters and the thinking at 2,432, all on the 2,000-character stretch.

## Longer repeats, and files written from a template

A review of the change measured text written for it (no owner data), streamed through the guard's own code:

- **Prose said again.** Real prose (excerpts of Clank's documents) compresses alone to 0.50-0.63, so a repeat of a
  longer stretch compresses less: over 8,000 characters, a unit of 600 characters comes to 0.045-0.056 (found), 800 to
  0.057-0.071 (mostly not), 1,500 to 0.094-0.117 (never). A repeat that counts up ("check n = 41 again") stays near
  0.064; one that circles among five sentences, 0.062. The long stretch finds prose said again every 600 to 800
  characters; longer or reworded repeats run on.
- **Files written from a template**, as a tool call's arguments: records that differ only by an id 0.032-0.047 over
  8,000 characters and 0.072-0.124 over 2,000; a seat map 0.037-0.042; table rows with placeholder names 0.039-0.041; a
  compose file of 24 near-identical services 0.046-0.047; ordinary CSV, Markdown and LaTeX tables, SVG, imports and
  logs 0.07-0.47. Over 8,000 characters these would be stopped, and stopped again each time they are asked again; over
  2,000 none is. A literal 56×56 identity matrix comes to 0.038 over 2,000 and would be stopped, as the list of zeros.

## Result

A part of an answer repeats itself when one of its newest stretches compresses to under **0.06** of its size: 2,000
and 8,000 characters of the thinking and the text, 2,000 of a tool call's arguments (files written from a template
compress as far as a loop over 8,000). All three loops are found, at 2,176 and 2,432 characters (some 15 seconds,
instead of 16,384 tokens and 3.7 minutes); prose said again every 600 to 800 characters by the long stretch; no
ordinary answer came under 0.188 and Clank's most repetitive file stays at 0.097 (margins of three and 1.6 times),
templated files at 0.072 or more in tool calls (1.25 times). Decision 0040; design 0004 §2.
