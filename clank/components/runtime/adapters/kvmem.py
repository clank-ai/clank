"""KVMem/llama.cpp (`kvmem-llamacpp`): the llama.cpp fork that keeps a long context by retrieving older KV from system
memory (design 0003 §4, decision 0010).

Written for v0.16.0-rc1 (commit `db4bc22`), whose `llama-kvmem-server --help` its recording holds. It runs one request
at a time; vision takes a projector file (`--mmproj`), on the GPU or the CPU; speculation drafts with the model's MTP
head. Clank's defaults for it are the ones measured best on an RTX 5080 (PROTOTYPE.md): a 262K context, a 36K exact
window, MTP with 3 draft tokens, thinking on with a 4096-token budget; CUDA graphs are off, the owner's decision of
2026-10-08 after three crashes on an MTP verify step. It is ready when its log says `listening on`; its log reports
what each GPU buffer took.

Its GPU layers (`-ngl`) and its sampling (`--temp` and the rest) have no default of Clank's (design 0003 §4.1, decision
0119): unset, KVMem gets no flag and keeps its own, 99 layers (every one) and Qwen3.8-27B's model card's sampling,
chosen per request by thinking mode (temperature 1.0 thinking and 0.7 not, top_p 0.95 and 0.80, presence penalty 0 and
1.5), which each option says in words. Its server gives a request its mode's defaults, then the flags, then the
request's own fields (`tools/kvmem-chat-sampling.h`), so a flag holds for both modes and is given even at a value one
mode's default has, and a request's own value wins over it.

Its KV cache holds `kvmem.budget` plus `kvmem.gen_reserve` cells, each taking, for every attention layer, a key and a
value of the model's KV width at the cache type's bits per value; the model's facts come from the catalog. With a budget
of 0 it holds the whole context and no more: KVMem caps its pool at the context then (`kvmem_compute_pool` in
`src/adapter/llama-memory-kvmem.cpp`), so every token is attended exactly until a prompt passes 95% of the context (its
high watermark), where retrieval would begin; an agent that keeps room for its answer stays below it. KVMem also caps
the pool at half the GPU's memory, which binds only past about 245,000 tokens at q8_0 on a 16 GB card, so the estimate
leaves it out. With MTP on, the model's MTP head keeps a pool of its own with as many cells, at f16
(`mtp_bytes_per_cell` in the catalog: one layer, a key and a value of the KV width); the estimate counts it with the
buffers, and the log reports it on its `KVMEM_TRACE mtp_pool` line. The compute buffers grow with the cells too
(`compute_bytes_per_cell`: Qwen3.8's took 374.28 MiB at 53,248 cells and 594.28 MiB at 98,304, a fixed part and
5,120 bytes a cell), so the catalog's `buffers_mib` holds only the fixed parts: the recurrent state and that base.

With a budget, an answer is written into the generation reserve once older context has been retrieved (the working set
is pinned), and KVMem v0.16 fails the request when the reserve fills ("no free GPU slot for block N"); nothing in KVMem
checks `max_tokens` against it. So a preset with a budget is refused when its `max_output` is more than its reserve
(0 is KVMem's own 256). With a budget of 0 its pool is the whole context and the rule does not apply.

Its context facts (design 0012 §4, §4.4): with a budget, it attends exactly that many tokens on the GPU, in blocks of
128 with the first block always kept, the others picked by their likeness to the last user message (`retrieval`) or the
newest (`recency`), the rest waiting in system memory (the measurement of 2026-10-15: "daily 262K" keeps 288 blocks of
128 tokens); with a budget of 0, its whole window. It keeps one conversation: a request that shares no checkpoint with
it resets its store (design 0012 §3). It has no route that counts tokens (it serves `/health`, `/v1/models` and
`/v1/chat/completions`), and reports only totals, in its answer's usage, the cache's hits in `prompt_cache_hit_tokens`.
It refuses a request whose prompt and `max_tokens` together pass its window with HTTP 400 and
`{"error":"prompt + max_tokens exceeds n_ctx"}` (`FULL`, read in its server, `tools/llama-kvmem-server.cpp`; decision
0090), words OpenCode does not read as a context overflow, so the gateway answers it as one.
"""

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from clank.components.runtime.adapters.engine import (
    ANY,
    ContextFacts,
    EngineAdapter,
    EngineOption,
    EngineVersion,
    ExactWindow,
    Launch,
    MemoryEstimate,
    OptionValue,
    Plan,
)

BITS = {"f16": 16.0, "q8_0": 8.5, "q5_0": 5.5, "q4_0": 4.5}
BUFFER = re.compile(r"\b(CUDA\d+) (model|KV|RS|compute) buffer size =\s*([\d.]+) MiB")
MTP_POOL = re.compile(r"\bKVMEM_TRACE mtp_pool cells=\d+ .*?\bbytes=(\d+)")
REPORTED = {"model": "weights", "KV": "kv", "RS": "recurrent", "compute": "compute"}
MIB = 1024 * 1024
BLOCK = 128  # tokens in one of its blocks; the first block is always on the GPU
PICKS = {"retrieval": "by likeness to the last user message", "recency": "the most recent"}
FULL_WORDS = "prompt + max_tokens exceeds n_ctx"  # its error when a prompt and its max_tokens pass the window
FIELDS = {
    "prompt": "usage.prompt_tokens",
    "output": "usage.completion_tokens",
    "cached": "usage.prompt_cache_hit_tokens",
}
BOTH = "; set, it holds with thinking on and off"  # said of a sampling option whose default differs by mode
# Its sampling, unset unless a preset sets it (design 0003 §4.1, decision 0119): its own defaults, Qwen3.8-27B's model
# card's, thinking and not, in words; the bounds its server checks (`tools/kvmem-chat-sampling.h`).
SAMPLING = (
    EngineOption(
        "sampling.temperature", "Temperature", f"How random each token is: 0 always takes the likeliest{BOTH}.",
        "number", None, {ANY: ("--temp", "{value}")}, minimum=0, maximum=2,
        engine_default_words="1.0 thinking, 0.7 not thinking",
    ),
    EngineOption(
        "sampling.top_p", "Top p", f"Tokens are drawn from the likeliest that hold this share of the chance{BOTH}.",
        "number", None, {ANY: ("--top-p", "{value}")}, minimum=0, maximum=1,
        engine_default_words="0.95 thinking, 0.80 not thinking",
    ),
    EngineOption(
        "sampling.top_k", "Top k", "Tokens are drawn from at most this many of the likeliest; 0 for no limit.",
        "integer", None, {ANY: ("--top-k", "{value}")}, minimum=0, maximum=2**31 - 1,
        engine_default_words="20 (thinking or not)",
    ),
    EngineOption(
        "sampling.min_p", "Min p", "Tokens less likely than this share of the likeliest one's chance are left out.",
        "number", None, {ANY: ("--min-p", "{value}")}, minimum=0, maximum=1, engine_default_words="0 (none)",
    ),
    EngineOption(
        "sampling.presence_penalty", "Presence penalty",
        f"Lowers every token already written, so an answer moves on rather than loops{BOTH}.",
        "number", None, {ANY: ("--presence-penalty", "{value}")}, minimum=-2, maximum=2,
        engine_default_words="0 thinking, 1.5 not thinking",
    ),
    EngineOption(
        "sampling.frequency_penalty", "Frequency penalty", "Lowers a token the more often it was written.",
        "number", None, {ANY: ("--frequency-penalty", "{value}")}, minimum=-2, maximum=2,
        engine_default_words="0 (none)",
    ),
    EngineOption(
        "sampling.repeat_penalty", "Repeat penalty",
        "Divides the chance of tokens written recently: 1 for none, above 1 against repeats.",
        "number", None, {ANY: ("--repeat-penalty", "{value}")}, more_than=0, engine_default_words="1 (none)",
    ),
    EngineOption(
        "sampling.seed", "Seed", "The random seed: the same seed and request give the same answer.",
        "integer", None, {ANY: ("--seed", "{value}")}, minimum=0, maximum=2**32 - 1,
        engine_default_words="random, for each request",
    ),
)  # fmt: skip


class KvmemLlamacpp(EngineAdapter):
    """KVMem/llama.cpp's server."""

    NAME = "kvmem-llamacpp"
    LABEL = "KVMem/llama.cpp"
    PROGRAM = "llama-kvmem-server"
    FORMAT = "gguf"
    FULL = (FULL_WORDS,)
    VERSIONS = (
        EngineVersion(
            "v0.16.0-rc1",
            {
                "requests at once": "1",
                "vision": "yes, with a projector file, on the GPU or the CPU",
                "speculation": "the model's MTP head (draft-mtp)",
                "context": "up to the model's 262,144 tokens, older context retrieved from system memory",
            },
            source="commit db4bc22ee6e8f4b590188dcc0457e72022eb1bbe",
        ),
    )

    def options(self) -> list[EngineOption]:
        """Its launch options at v0.16.0-rc1."""
        return [
            EngineOption(
                "context", "Context", "Tokens the model can see; past the budget, older context is retrieved.",
                "integer", 262144, {ANY: ("-c", "{value}")}, minimum=2048, maximum=262144, unit="tokens",
                memory="none on the GPU beyond the budget; system memory for what is retrieved", engine_default=2048,
                tested=(262144,),
            ),
            EngineOption(
                "max_output", "Maximum output", "The most tokens one answer may have, when a request does not say.",
                "integer", 16384, {ANY: ("-n", "{value}")}, minimum=1, unit="tokens", engine_default=128,
            ),
            EngineOption(
                "gpu_layers", "GPU layers",
                "The model's layers on the GPU; the others stay in system memory, read by the CPU for every token.",
                "integer", None, {ANY: ("-ngl", "{value}")}, minimum=0, unit="layers",
                memory="the weights of the layers left off the GPU go to system memory (an estimate)",
                engine_default=99, engine_default_words="99: every layer on the GPU",
            ),
            EngineOption(
                "kvmem.budget", "Retrieval budget", "Tokens attended to exactly on the GPU; 0 means the whole context.",
                "integer", 36864, {ANY: ("--kvmem-budget", "{value}")}, minimum=0, unit="tokens",
                memory="KV bytes per token, times the budget and the reserve", engine_default=0, tested=(24576, 36864),
            ),
            EngineOption(
                "kvmem.gen_reserve", "Generation reserve", "Room kept on the GPU for the answer being written.",
                "integer", 16384, {ANY: ("--kvmem-gen-reserve", "{value}")}, minimum=0, unit="tokens",
                memory="KV bytes per token, times the reserve", engine_default=256,
            ),
            EngineOption(
                "kvmem.method", "Retrieval method", "How older context is chosen: by relevance, or the most recent.",
                "choice", "retrieval", {ANY: ("--kvmem-method", "{value}")}, choices=("retrieval", "recency"),
                engine_default="retrieval",
            ),
            EngineOption(
                "kv.type", "KV cache type", "The cache's number format: q4_0 takes half of q8_0, maybe at a cost.",
                "choice", "q8_0", {ANY: ("--kv-dtype", "{value}")}, choices=("f16", "q8_0", "q5_0", "q4_0"),
                memory="bits per value: f16 16, q8_0 8.5, q5_0 5.5, q4_0 4.5", engine_default="q8_0", tested=("q8_0",),
            ),
            EngineOption(
                "spec.type", "Speculation", "Draft tokens with the model's MTP head, checked in one step.",
                "choice", "draft-mtp", {ANY: ("--spec-type", "{value}")}, choices=("none", "draft-mtp"),
                engine_default="none", tested=("draft-mtp", "none"),
            ),
            EngineOption(
                "spec.draft_tokens", "Draft tokens", "Tokens drafted per step; 3 is the tested value.",
                "integer", 3, {ANY: ("--spec-draft-n-max", "{value}")}, minimum=1, maximum=8,
                requires=("spec.type=draft-mtp",), engine_default=3, tested=(2, 3, 4),
            ),
            EngineOption(
                "vision", "Vision", "Images in: off, the projector on the CPU, or on the GPU (0.6 GB more there).",
                "choice", "off",
                {
                    "off": (),
                    "cpu": ("--mmproj", "{projector}", "--no-mmproj-offload"),
                    "gpu": ("--mmproj", "{projector}"),
                },
                choices=("off", "cpu", "gpu"), memory="gpu: the projector's size", tested=("cpu", "gpu"),
            ),
            EngineOption(
                "vision.max_tokens", "Image tokens", "The most tokens one image may take.",
                "integer", None, {ANY: ("--image-max-tokens", "{value}")}, minimum=64, unit="tokens",
                requires=("vision",), tested=(512,),
            ),
            EngineOption(
                "thinking", "Thinking", "The model thinks before it answers, unless a request turns it off.",
                "switch", True, {"true": ("--enable-thinking",), "false": ()},
            ),
            EngineOption(
                "thinking.budget", "Thinking budget", "The most tokens of thinking; -1 for no limit.",
                "integer", 4096, {ANY: ("--reasoning-budget", "{value}")}, minimum=-1, unit="tokens",
                requires=("thinking",), engine_default=-1,
            ),
            *SAMPLING,
            EngineOption(
                "batch", "Batch", "Tokens read per step while reading a prompt.",
                "integer", 512, {ANY: ("-b", "{value}")}, minimum=32, engine_default=512,
            ),
            EngineOption(
                "cuda_graphs", "CUDA graphs", "Faster decoding; off because they crashed v0.16 on an MTP verify step.",
                "switch", False, {"false": ("env:GGML_CUDA_DISABLE_GRAPHS=1",), "true": ()}, tested=(False,),
            ),
        ]  # fmt: skip

    def validate(self, options: Mapping[str, object]) -> list[str]:
        """Each option's own problems, then the rule between the reserve and the longest answer (module docstring)."""
        problems = super().validate(options)
        if problems:
            return problems
        values = self.resolved(cast(Mapping[str, OptionValue], options))
        output, reserve = int(values["max_output"]), int(values["kvmem.gen_reserve"]) or 256
        if int(values["kvmem.budget"]) and output > reserve:
            problems.append(
                f"max_output ({output:,}) is more than kvmem.gen_reserve ({reserve:,}): with a budget, KVMem v0.16 "
                "fails an answer that outgrows its reserve once it has retrieved older context; raise the reserve or "
                "lower the output"
            )
        return problems

    def translate(self, body: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """llama.cpp's fields: thinking on or off in `chat_template_kwargs.enable_thinking`, the reasoning budget in
        `reasoning_budget_tokens`."""
        found, notes = copy.deepcopy(dict(body)), []
        if "enable_thinking" in found:
            kwargs = dict(found.get("chat_template_kwargs") or {})
            kwargs["enable_thinking"] = found.pop("enable_thinking")
            found["chat_template_kwargs"] = kwargs
            notes.append("enable_thinking became chat_template_kwargs.enable_thinking")
        if "reasoning_budget" in found:
            found["reasoning_budget_tokens"] = found.pop("reasoning_budget")
            notes.append("reasoning_budget became reasoning_budget_tokens")
        return found, notes

    def plan(self, options: Mapping[str, OptionValue], launch: Launch) -> Plan:
        """`llama-kvmem-server -m MODEL <options> --host ADDRESS --port PORT`, in its install folder, with its
        libraries on the path."""
        argv, env = self.arguments(options, launch.facts)
        if "library_path" in launch.facts:
            env["LD_LIBRARY_PATH"] = launch.facts["library_path"]
        command = (
            *launch.program,
            "-m",
            launch.model_path,
            *argv,
            "--host",
            launch.address,
            "--port",
            str(launch.port),
        )
        return Plan(command, env, launch.facts.get("folder", ""), launch.port, self.memory(options, launch))

    def memory(self, options: Mapping[str, OptionValue], launch: Launch) -> MemoryEstimate:
        """The GPU memory a launch takes: the model's weights, the KV slot pool, the buffers, the engine's overhead."""
        values = self.resolved(options)
        sizes = launch.sizes
        budget = int(values["kvmem.budget"])
        cells = int(values["context"]) if budget == 0 else budget + int(values["kvmem.gen_reserve"])
        per_cell = sizes.get("attention_layers", 0) * 2 * sizes.get("kv_width", 0) * BITS[str(values["kv.type"])] / 8
        projector = sizes.get("projector_mib", 0) if values["vision"] == "gpu" else 0
        notes = [f"KV: {cells:,} cells of {per_cell:,.0f} bytes ({values['kv.type']})"]
        mtp = sizes.get("mtp_bytes_per_cell", 0) if values["spec.type"] == "draft-mtp" else 0
        if mtp:
            notes.append(f"the MTP head's pool, with the buffers: {cells:,} cells of {mtp:,.0f} bytes (f16)")
        compute = sizes.get("compute_bytes_per_cell", 0)
        if compute:
            notes.append(f"the compute buffers' growth, with the buffers: {cells:,} cells of {compute:,.0f} bytes")
        return MemoryEstimate(
            weights_mib=round(sizes.get("gpu_weights_mib", 0)),
            kv_mib=round(cells * per_cell / MIB),
            buffers_mib=round(sizes.get("buffers_mib", 0) + projector + cells * (mtp + compute) / MIB),
            overhead_mib=round(sizes.get("overhead_mib", 0)),
            notes=tuple(notes),
        )

    def ready(self, line: str) -> bool:
        """`llama-kvmem-server listening on http://...`."""
        return "listening on http://" in line

    def memory_report(self, lines: Sequence[str]) -> dict[str, float]:
        """The GPU buffers its log reports: weights, KV, recurrent state, compute and the MTP head's pool, in MiB."""
        found: dict[str, float] = {}
        for line in lines:
            if (match := BUFFER.search(line)) is not None:
                name = REPORTED[match.group(2)]
                found[name] = found.get(name, 0.0) + float(match.group(3))
            elif (match := MTP_POOL.search(line)) is not None:
                found["mtp"] = int(match.group(1)) / MIB
        return found

    def context_facts(self, options: Mapping[str, OptionValue]) -> ContextFacts:
        """Its window, its longest answer and its thinking budget; its retrieval budget as the window it attends to
        exactly on the GPU (none with a budget of 0: the whole context); one conversation, no counting, totals in its
        usage (module docstring)."""
        values = self.resolved(options)
        budget = int(values["kvmem.budget"])
        thinking = int(values.get("thinking.budget", -1)) if values.get("thinking") else -1
        exact = ExactWindow(budget, BLOCK, BLOCK, PICKS[str(values["kvmem.method"])]) if budget else None
        return ContextFacts(
            window=int(values["context"]), output=int(values["max_output"]),
            thinking_budget=thinking if thinking >= 0 else None, exact=exact, on_gpu=True, counts_tokens=False,
            one_conversation=True, fields=dict(FIELDS),
            full=f'HTTP 400, {{"error": "{FULL_WORDS}"}}, when a prompt and its max_tokens pass the window',
            source=f"{self.LABEL} {self.version.name}'s options and server; blocks of {BLOCK} tokens as measured on "
            "2026-10-15 (docs/measurements/2026-10-15-kvmem-long-tool-results.md)",
        )  # fmt: skip
