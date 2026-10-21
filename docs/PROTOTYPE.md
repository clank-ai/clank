# Clank's prototype

Clank began from an earlier private prototype: scripts and services on one Windows computer that ran a local model,
recorded its requests through a gateway, showed its work in a monitor, and ran an agent in a sandbox. Clank is a
product of its own (decision [0001](decisions/0001-clank-is-its-own-product.md)) and needs nothing from the prototype
(decision [0033](decisions/0033-clank-needs-nothing-from-its-prototype.md)): what came over was redesigned part by
part, with machine-specific values replaced by configuration.

## Lessons measured in the prototype

Facts that cost time to find. Each one constrains a design.

- **Desktop composition takes GPU time from the model.** With a high-refresh display, a page redrawing every frame cut
  decoding from about 50 to 17 tokens per second (2026-10-08). On 2026-10-11, decoding ran at half its benchmark speed
  while the desktop compositor used 23-46% of the GPU. Clank's own views never animate endlessly.
- **Hardware-accelerated GPU scheduling (HAGS) froze the Windows desktop** for up to 31 seconds while a long prompt was
  read; with HAGS off, no freezes (2026-10-08). The setup guide checks it.
- **KVMem keeps an exact attention window of 36,864 tokens** and retrieves older context; agent sessions beyond about
  80,000 tokens slow down, and at 164,000 tokens a request failed to find room in the window (2026-10-11).
- **Small side requests evict a single-slot server's cache.** The agent's title requests made the next real request
  re-read its whole context; the gateway answers them itself.
- **CUDA graphs crashed KVMem's server** on the first speculative-decoding verify step after a long prompt with tools
  (KVMem v0.16, 2026-10-07); they are off there, at a cost the setup must measure.
- **On Windows, Docker Desktop must start before WSL**, or WSL loses its ability to run Windows programs.
- **Speed must be measured the same way every time** (a fixed prompt, a fixed length, the server's own numbers), or
  changes cannot be compared.
