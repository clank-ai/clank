"""llama.cpp's own server (`llamacpp`): upstream `llama-server`, its CPU build, for the `fast` slot's completion
(design 0006 §3, decision 0035).

Written for build b11588 (2026-10-13), whose `--help` and startup its recording holds; Clank installs the release's CPU
archive for Ubuntu x64 by its recipe. It serves OpenAI's chat completions and its own fill in the middle (`/infill`),
which completion in VS Code uses. Clank's defaults for it are the ones measured on this computer (the measurement of
2026-10-15): six threads, an 8,192-token context, one request at a time, cache reuse in chunks of 256 tokens; its
threads at a low priority and without polling, so the owner's programs come first and it takes no CPU while it waits;
no web page of its own. It is ready when its log says `listening on`; at verbosity 4 its log reports its buffers, all in
system memory: it takes nothing of the GPU, so the GPU's fit does not hold it back (`MemoryEstimate.on_gpu`).

Its sampling (`--temp` and the rest, the keys KVMem's adapter has) has no default of Clank's (design 0003 §4.1,
decision 0119): unset, it gets no flag and keeps its own defaults, which its `--help` gives, or the model file's own
where the file carries one (`general.sampling.temp`, `top_p`, `top_k`, `min_p` and `penalty_repeat`, which its library
reads); each option says which in words. A flag set wins over the model file's, and a request's own fields over both.

Its context facts (design 0012 §4): it attends its whole window, in system memory; it counts tokens (`/tokenize`); it
may keep more than one conversation (its slots, and earlier prompts it keeps in system memory), so another's request
does not surely make it read the next one again. Its answer reports the prompt and the answer in its usage, and the
tokens it took from its cache in its `timings` (`cache_n`), as its server's source reads. It refuses a request its
context cannot hold with HTTP 400 and an error of type `exceed_context_size_error`, "request (N tokens) exceeds the
available context size (M tokens), try increasing it" (`FULL`, read in its server's program, build 11610; decision
0090).
"""

import re
from collections.abc import Mapping, Sequence

from clank.components.runtime.adapters.engine import (
    ANY,
    ContextFacts,
    EngineAdapter,
    EngineOption,
    EngineVersion,
    Launch,
    MemoryEstimate,
    OptionValue,
    Plan,
)

BUFFER = re.compile(r"\bCPU(?:_Mapped)? (model|KV|compute) buffer size =\s*([\d.]+) MiB")
REPORTED = {"model": "weights", "KV": "kv", "compute": "compute"}
MIB = 1024 * 1024
COMPUTE_MIB = 91  # its compute buffer with a 1,024-token batch, as the recorded startup reports it
FIELDS = {
    "prompt": "usage.prompt_tokens",
    "output": "usage.completion_tokens",
    "cached": "timings.cache_n",
    "timings": "timings",
}
FILE = ", or the model file's own"  # a default a model file may replace (`general.sampling.*`)
# Its sampling, unset unless a preset sets it (design 0003 §4.1, decision 0119): its own defaults as its `--help` gives
# them, in words; bounded as each value's meaning bounds it, its penalties not, as its help leaves them.
SAMPLING = (
    EngineOption(
        "sampling.temperature", "Temperature", "How random each token is: 0 always takes the likeliest.",
        "number", None, {ANY: ("--temp", "{value}")}, minimum=0, engine_default_words=f"0.80{FILE}",
    ),
    EngineOption(
        "sampling.top_p", "Top p", "Tokens are drawn from the likeliest that hold this share of the chance.",
        "number", None, {ANY: ("--top-p", "{value}")}, minimum=0, maximum=1, engine_default_words=f"0.95{FILE}",
    ),
    EngineOption(
        "sampling.top_k", "Top k", "Tokens are drawn from at most this many of the likeliest; 0 for no limit.",
        "integer", None, {ANY: ("--top-k", "{value}")}, minimum=0, engine_default_words=f"40{FILE}",
    ),
    EngineOption(
        "sampling.min_p", "Min p", "Tokens less likely than this share of the likeliest one's chance are left out.",
        "number", None, {ANY: ("--min-p", "{value}")}, minimum=0, maximum=1, engine_default_words=f"0.05{FILE}",
    ),
    EngineOption(
        "sampling.presence_penalty", "Presence penalty",
        "Lowers every token already written, so an answer moves on rather than loops.",
        "number", None, {ANY: ("--presence-penalty", "{value}")}, engine_default_words="0.00 (none)",
    ),
    EngineOption(
        "sampling.frequency_penalty", "Frequency penalty", "Lowers a token the more often it was written.",
        "number", None, {ANY: ("--frequency-penalty", "{value}")}, engine_default_words="0.00 (none)",
    ),
    EngineOption(
        "sampling.repeat_penalty", "Repeat penalty",
        "Divides the chance of tokens written recently: 1 for none, above 1 against repeats.",
        "number", None, {ANY: ("--repeat-penalty", "{value}")}, more_than=0,
        engine_default_words=f"1.00 (none){FILE}",
    ),
    EngineOption(
        "sampling.seed", "Seed", "The random seed: the same seed and request give the same answer; -1 for random.",
        "integer", None, {ANY: ("--seed", "{value}")}, minimum=-1, maximum=2**32 - 1,
        engine_default_words="-1: random",
    ),
)  # fmt: skip


class LlamaCpp(EngineAdapter):
    """llama.cpp's server, on the CPU."""

    NAME = "llamacpp"
    LABEL = "llama.cpp"
    TOKENIZE = "/tokenize"
    PROGRAM = "llama-server"
    FORMAT = "gguf"
    FULL = ("exceed_context_size_error",)
    VERSIONS = (
        EngineVersion(
            "b11588",
            {
                "requests at once": "as many as its slots (-np); Clank's completion preset serves one",
                "vision": "no (this build is for completion: no projector is given)",
                "speculation": "no",
                "fill in the middle": "yes, /infill, for models trained for it",
                "device": "the CPU (the release's CPU build)",
            },
            source="release b11588, commit 7f51953d7",
        ),
    )

    def options(self) -> list[EngineOption]:
        """Its launch options at b11588."""
        return [
            EngineOption(
                "context", "Context", "Tokens the model can see at once: the file around the cursor fits in 8,192.",
                "integer", 8192, {ANY: ("-c", "{value}")}, minimum=512, unit="tokens",
                memory="system memory: KV bytes per token, times the context", engine_default=0, tested=(8192,),
            ),
            EngineOption(
                "threads", "Threads", "CPU threads it computes with: 6 serve a line in about 0.3 s.",
                "integer", 6, {ANY: ("-t", "{value}")}, minimum=1, maximum=64, engine_default=-1, tested=(4, 6, 8, 12),
            ),
            EngineOption(
                "parallel", "Requests at once", "Its slots; completion needs one, since only the newest one counts.",
                "integer", 1, {ANY: ("-np", "{value}")}, minimum=1, maximum=16, engine_default=-1, tested=(1,),
            ),
            EngineOption(
                "cache_reuse", "Cache reuse", "Reuse what it read before in chunks of this many tokens, shifted.",
                "integer", 256, {ANY: ("--cache-reuse", "{value}")}, minimum=0, unit="tokens", engine_default=0,
                tested=(256,),
            ),
            EngineOption(
                "batch", "Batch", "Tokens read per step while reading a prompt.",
                "integer", 1024, {ANY: ("-b", "{value}")}, minimum=32, engine_default=2048, tested=(1024,),
            ),
            EngineOption(
                "ubatch", "Physical batch", "Tokens computed at once while reading a prompt.",
                "integer", 1024, {ANY: ("-ub", "{value}")}, minimum=32, engine_default=512, tested=(1024,),
            ),
            EngineOption(
                "max_output", "Maximum output", "The most tokens one answer may have, when a request does not say.",
                "integer", 128, {ANY: ("-n", "{value}")}, minimum=1, unit="tokens", engine_default=-1,
            ),
            *SAMPLING,
            EngineOption(
                "priority", "Priority", "Its threads' priority: low lets the computer's other programs go first.",
                "choice", "low", {"low": ("--prio", "-1"), "normal": ()}, choices=("low", "normal"),
                tested=("low",),
            ),
            EngineOption(
                "polling", "Polling", "Threads that wait for work spin (0 to 100); 0 takes no CPU while waiting.",
                "integer", 0, {ANY: ("--poll", "{value}")}, minimum=0, maximum=100, engine_default=50, tested=(0,),
            ),
            EngineOption(
                "web_page", "Web page", "Its own chat page in a browser; Clank's clients do not need it.",
                "switch", False, {"false": ("--no-webui",), "true": ()},
            ),
            EngineOption(
                "log_level", "Log level", "Its log's verbosity: 4 adds what memory it took, which Clank reads.",
                "integer", 4, {ANY: ("-lv", "{value}")}, minimum=0, maximum=5, engine_default=3,
            ),
            EngineOption(
                "vision", "Vision", "Images in: on reads them with the model's projector file (on the CPU).",
                "choice", "off", {"off": (), "on": ("--mmproj", "{projector}")}, choices=("off", "on"),
                tested=("on",),
            ),
            EngineOption(
                "vision.max_tokens", "Image tokens", "The most tokens one image may take: more reads finer detail.",
                "integer", None, {ANY: ("--image-max-tokens", "{value}")}, minimum=64, unit="tokens",
                requires=("vision=on",), tested=(1024,),
            ),
        ]  # fmt: skip

    def plan(self, options: Mapping[str, OptionValue], launch: Launch) -> Plan:
        """`llama-server -m MODEL <options> --host ADDRESS --port PORT`, in its install folder, with its libraries
        on the path."""
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
        """The system memory a launch takes (none of the GPU): the model's file, mapped (and its projector, with
        vision on); its KV cache in f16; its compute buffer."""
        values = self.resolved(options)
        sizes = launch.sizes
        per_token = sizes.get("attention_layers", 0) * 2 * sizes.get("kv_width", 0) * 2
        kv = int(values["context"]) * per_token
        projector = sizes.get("projector_mib", 0) if values.get("vision") == "on" else 0
        return MemoryEstimate(
            weights_mib=round(sizes.get("weights_mib", 0) + projector),
            kv_mib=round(kv / MIB),
            buffers_mib=COMPUTE_MIB,
            overhead_mib=0,
            notes=(
                f"in system memory, none on the GPU; KV: {int(values['context']):,} tokens of {per_token:,.0f} bytes",
            ),
            on_gpu=False,
        )

    def ready(self, line: str) -> bool:
        """`llama_server: listening on http://...`."""
        return "listening on http://" in line

    def memory_report(self, lines: Sequence[str]) -> dict[str, float]:
        """The buffers its log reports (at verbosity 4): the mapped weights, KV and compute, in MiB of system memory."""
        found: dict[str, float] = {}
        for line in lines:
            if (match := BUFFER.search(line)) is not None:
                name = REPORTED[match.group(1)]
                found[name] = found.get(name, 0.0) + float(match.group(2))
        return found

    def context_facts(self, options: Mapping[str, OptionValue]) -> ContextFacts:
        """Its window and its longest answer; its whole window attended, in system memory; it counts tokens; its cache
        in its timings (module docstring)."""
        values = self.resolved(options)
        return ContextFacts(
            window=int(values["context"]), output=int(values["max_output"]), thinking_budget=None, exact=None,
            on_gpu=False, counts_tokens=True, one_conversation=False, fields=dict(FIELDS),
            full="HTTP 400, an error of type exceed_context_size_error, when a prompt passes the window",
            source=f"{self.LABEL} {self.version.name}'s options and its server's source (its usage and `timings`)",
        )  # fmt: skip
