# Measurements

What was measured on the owner's machine, how, and what it showed: one document per measurement, named by its date
and subject. The numbers in designs and presets cite these.

| Measurement | What |
| --- | --- |
| [NInfer and KVMem](2026-10-13-ninfer-and-kvmem.md) | Both serving setups compared: speed by prompt size, recall, capabilities, ten coding tasks |
| [The model battery](2026-10-15-model-battery.md) | Thirteen tasks of studies and code changes in a simulator's repository: outcomes, speed, what to fix |
| [Completion on the CPU](2026-10-15-completion-on-the-cpu.md) | What the main slot can serve for completion, and two small fill-in-the-middle models on the CPU: time per line by threads |
| [The NVIDIA driver](2026-10-14-the-nvidia-driver.md) | Why KVMem crashed on clearing its cache after a driver update, and the retest on an earlier driver |
| [KVMem and a long tool result](2026-10-15-kvmem-long-tool-results.md) | Why one tool result larger than the GPU budget failed the request, the upstream fix applied, and the check before and after |
| [Vision on the CPU](2026-10-15-vision-on-the-cpu.md) | Two models that read images, on the CPU: start, reading time, memory, and how well they read marks on a figure |
| [Repetition in the answers](2026-10-18-repetition-in-answers.md) | How much real answers and three real loops compress over a short and a long stretch: where the loop guard stops an answer, and the margin to ordinary work |
| [The frontier preset](2026-10-18-the-frontier-preset.md) | Swift 1.5's file checked, what KVMem allocates with the whole context attended exactly, how much context fits beside this desktop, and its speed on the GPU |
| [OpenCode and a full context](2026-10-20-opencode-and-a-full-context.md) | Why a long session failed at the context's limit: when OpenCode compacts, the tokens of one tool output as it cuts them, and which errors it compacts on, read and run in OpenCode 1.19.0 |
| [The cost of the context's estimate](2026-10-20-the-estimates-cost.md) | What the gateway's census of a 262,144-token request and the service's estimate from it cost on the CPU, on synthetic requests: about 8 ms a request, about 40 ms at the worst seen (one huge item), in a worker thread |
