"""OpenCode (`opencode`, its terminal interface), the first agent program (decision 0011, design 0004 §4).

Its configuration (`~/.config/opencode/opencode.json` in the container's home) has one provider, `clank`, OpenAI's API
at the gateway through the edge, its key the workspace's own there (design 0016 §9), with one model: the role the
gateway routes (`agent`), named after the preset that runs it, with its context (the engine's window less the margin
kept for one step's tool results, decision 0089) and output limits, its reasoning (interleaved, as llama.cpp's
`reasoning_content`), tool calls, and images when its model reads them (else OpenCode sends it none). It is OpenCode's
only provider; OpenCode may not touch anything outside the folder, and has no web tools (the container has no route
out). OpenCode runs offline: no updates, no fetch of its list of models, no downloads of language servers, no default
plugins, no sharing, no reading of another assistant's files, and no file watcher (slow across Docker's mount of a
Windows folder). These choices were measured with OpenCode in the prototype's sandbox (PROTOTYPE.md); its version is the
image's. The MCP servers it gets (design 0004 §10) are its `mcp`, each a `local` command it starts in the container with
its environment; OpenCode reads no `.mcp.json` of its own. It asks before every change to a file (`edit: ask`): Clank
answers, after the owner's review or at once in auto mode (design 0007 §3).

Its agents are OpenCode's `build`, and Clank's `planner` in place of OpenCode's `plan` (design 0009 §3, decision 0038),
so Tab switches between Build and Planner. The planner's instructions are `prompts/planner.md`; its rules, its own and
so the last OpenCode reads (the last that matches wins): it may write Markdown and nothing else, and no Markdown that
another agent or assistant loads as its settings or instructions (`plans.SETTINGS`, `plans.INSTRUCTIONS`); it may run
the reading commands (`READING`, none with a flag that writes or runs a program), unless redirected, substituted or
told to write a file (`GUARDS`, which come after them; OpenCode checks each part of a chained or piped command on its
own); it may ask questions, use the `explore` subagent only (OpenCode's own reading tools search the folder), and use a
server's tools only when the server's last check marks them read-only, each named as OpenCode names an MCP tool
(`<server>_<tool>`, every other character than letters, digits, `_` and `-` made `_`). It never asks for a permission
(the owner, 2026-10-17): every rule allows or denies, so anything else, and a call repeated (`doom_loop`), is refused
at once, and the `explore` helper reads under the same rules. An edit the planner is denied is never asked about, so
auto mode cannot answer it. `/implement <plan>` is Clank's command: `build` carries the plan out
with the instructions of `prompts/implement.md` (§5). Every agent also reads Clank's instructions in the container
(`/opt/clank/instructions/`, from the sandbox image), the LaTeX rules first among them (design 0020 §13).

It compacts a session once a step's total (its prompt and its answer) reaches the window it is told less the output
limit, counted up to 32,000 (its `session/overflow.ts`), and a compaction keeps a summary and the newest turns up to
min(15,000, max(2,000, a quarter of that)) (its `session/compaction.ts`), as read in OpenCode 1.19.0 (design 0012
§4.1); Clank turns neither `compaction.auto` off nor `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` on, which would change
the rule. It cuts each tool's output at 2,000 lines or 51,200 bytes, the rest saved to a file (its `Truncate`), which
the margin's default is chosen by (decision 0089). Told the engine's window itself, a step that ended just under the
line had its results push the next request and its answer's room past the window, and KVMem refused it.
"""

import json
import re
from collections.abc import Mapping, Sequence
from importlib import resources
from typing import Any

from clank.components.agents.adapters.program import AgentModel, AgentProgram, Compaction
from clank.components.agents.plans import INSTRUCTIONS, SETTINGS
from clank.components.tools.service import Server
from clank.kernel.adapters import Capability

ENVIRONMENT = {
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_MODELS_FETCH": "1",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
    "OPENCODE_DISABLE_SHARE": "1",
    "OPENCODE_DISABLE_CLAUDE_CODE": "1",
    "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "1",
}
PROVIDER = "clank"
# Commands the planner may run: none has a flag that writes a file or runs a program (find's -exec and -delete, rg's
# --pre, sed's -i and w, sort's -o and tree's -o do: OpenCode's own read, glob, grep and list tools read instead).
READING = (
    "ls", "cat", "head", "tail", "wc", "grep", "echo", "pwd", "diff", "nl", "file", "stat", "du", "which",
    "git status", "git log", "git diff", "git show",
)  # fmt: skip
# A reading command redirected, substituted or told to write a file is refused. OpenCode checks each part of a chained
# or piped command on its own (measured, 1.19.0): reading commands piped together run, and any other part is refused.
GUARDS = ("*>*", "*$(*", "*`*", "*--output*")
OUTPUT_COUNTED = 32_000  # the output limit OpenCode keeps room for, at most (its OUTPUT_TOKEN_MAX)
KEPT_MOST, KEPT_LEAST = 15_000, 2_000  # what a compaction keeps of the newest turns, at most and at least
UNSAFE = re.compile(r"[^a-zA-Z0-9_-]")  # what OpenCode replaces in an MCP tool's name


CLANK_INSTRUCTIONS = "/opt/clank/instructions/*.md"  # Clank's to every agent, in the container (design 0020 §13)


def prompt(name: str) -> str:
    """One of the instructions Clank gives OpenCode's agents and commands (`prompts/`)."""
    return resources.files("clank.components.agents").joinpath("prompts", name).read_text(encoding="utf-8")


def reading_commands() -> dict[str, str]:
    """The shell commands the planner (and the explore helper) may run, all else refused: never asked."""
    rules = {"*": "deny"}
    for command in READING:
        rules |= {command: "allow", f"{command} *": "allow"}
    return rules | dict.fromkeys(GUARDS, "deny")


def planner_rules(servers: Sequence[str], read_only: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """The planner's rules, in the order OpenCode reads them (the last that matches wins)."""
    rules: dict[str, Any] = {
        "edit": {
            "*": "deny",
            "*.md": "allow",
            **{f"*{folder}/*": "deny" for folder in SETTINGS},
            **{f"*{name}": "deny" for name in INSTRUCTIONS},
        },
        "bash": reading_commands(),
        "doom_loop": "deny",
        "question": "allow",
        "task": {"*": "deny", "explore": "allow"},
    }
    for server in sorted(servers):
        named = UNSAFE.sub("_", server)
        rules[f"{named}_*"] = "deny"
        for tool in sorted(read_only.get(server, ())):
            rules[f"{named}_{UNSAFE.sub('_', tool)}"] = "allow"
    return rules


class OpenCode(AgentProgram):
    """OpenCode, in the sandbox image."""

    NAME = "opencode"
    LABEL = "OpenCode"
    PLATFORMS = ("linux",)

    def capabilities(self) -> list[Capability]:
        """Its terminal interface, configured for Clank's gateway."""
        return [Capability("terminal", True, "`opencode`, in the workspace's folder")]

    def argv(self, port: int | None = None) -> list[str]:
        """Its terminal interface; with `port`, its API served there on the container's loopback."""
        return ["opencode", *(["--port", str(port), "--hostname", "127.0.0.1"] if port else [])]

    def env(self) -> dict[str, str]:
        """Offline: nothing fetched, nothing shared, nothing watched."""
        return dict(ENVIRONMENT)

    def compaction(self, window: int, output: int, margin: int = 0) -> Compaction:
        """Once a step's total reaches the window it is told (the window less `margin`) less the output limit
        (counted up to 32,000); a summary and the newest turns kept, up to a quarter of that, between 2,000 and 15,000
        tokens (module docstring)."""
        line = window - margin - min(output or OUTPUT_COUNTED, OUTPUT_COUNTED)
        keeps = min(KEPT_MOST, max(KEPT_LEAST, line // 4))
        told = (
            f"the window it is told (the engine's less {margin:,} kept for one step's tool results)"
            if margin
            else "the window"
        )
        rule = (
            f"OpenCode compacts once a step's total reaches {told} less the output limit (counted up to "
            f"{OUTPUT_COUNTED:,}), and keeps a summary and the newest turns up to {keeps:,} tokens"
        )
        return Compaction(line, keeps, rule)

    def configuration(
        self,
        model: AgentModel,
        servers: Mapping[str, Server] | None = None,
        read_only: Mapping[str, Sequence[str]] | None = None,
    ) -> tuple[str, str]:
        """Clank's gateway as its one provider, the role as its one model; each MCP server it gets, a local command;
        the planner in place of OpenCode's `plan`, and `/implement`."""
        described = {
            "name": model.title,
            "reasoning": True,
            "tool_call": True,
            "attachment": model.images,
            "modalities": {"input": ["text", "image"] if model.images else ["text"], "output": ["text"]},
            "temperature": True,
            "interleaved": {"field": "reasoning_content"},
            "limit": {"context": model.context - model.margin, "output": model.output},
        }
        config: dict[str, Any] = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                PROVIDER: {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Clank",
                    "options": {"baseURL": model.url, "apiKey": model.key, "timeout": False},
                    "models": {model.name: described},
                }
            },
            "model": f"{PROVIDER}/{model.name}",
            "small_model": f"{PROVIDER}/{model.name}",
            "enabled_providers": [PROVIDER],
            "autoupdate": False,
            "share": "disabled",
            "permission": {"external_directory": "deny", "webfetch": "deny", "websearch": "deny", "edit": "ask"},
            "instructions": [CLANK_INSTRUCTIONS],
            "agent": {
                "plan": {"disable": True},
                "planner": {
                    "mode": "primary",
                    "description": "Plans a study with you and writes the plan in Markdown; no code, figures or runs",
                    "prompt": prompt("planner.md"),
                    "permission": planner_rules(list(servers or {}), read_only or {}),
                },
                # The helper the planner may call reads as it does, and asks nothing either.
                "explore": {"permission": {"edit": "deny", "bash": reading_commands(), "doom_loop": "deny"}},
            },
            "command": {
                "implement": {
                    "description": "Carry out a plan step by step: /implement <path of the plan>",
                    "agent": "build",
                    "template": prompt("implement.md"),
                },
            },
        }
        if servers:
            config["mcp"] = {name: self.server_entry(server) for name, server in sorted(servers.items())}
        return f"{self.HOME}/.config/opencode/opencode.json", json.dumps(config, indent=2) + "\n"

    def server_entry(self, server: Server) -> dict[str, object]:
        """A local command with its environment, started with the agent."""
        return {
            "type": "local",
            "command": [server.command, *server.args],
            "environment": dict(server.env),
            "enabled": True,
        }
