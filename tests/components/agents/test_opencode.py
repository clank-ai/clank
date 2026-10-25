"""Design 0004 §4 and design 0009 §3-§5: OpenCode's configuration has one provider, Clank's gateway at the edge, with
one model, the role `agent`, its limits the running preset's (so OpenCode compacts a conversation before the engine
refuses it); it is OpenCode's only provider; nothing outside the folder is OpenCode's to touch and it has no web tools
(there is no route out); and OpenCode runs offline: no updates, no model list, no downloads, no plugins, no sharing, no
watching of the folder (slow across Docker's mount of a Windows folder), no reading of another assistant's files.

Clank's planner replaces OpenCode's `plan`: it may write Markdown and nothing else, run reading commands, and use only
the MCP tools a server's last check marks read-only (named as OpenCode names them); it never asks for a permission (the
owner, 2026-10-17: "It should never be asking to do anything when it is in Plan mode"): anything else is refused at
once, and so is a call it repeats, for it and for the explore helper it may call. Its instructions say how to plan,
measure, fit the owner's limits and write each section of a plan, Deliverables last, and that it asks the owner only
questions about the plan. `/implement` hands a plan to `build`, with the instructions for carrying it out.

Design 0020 §13: every agent reads Clank's instructions in the container (`/opt/clank/instructions/`), the LaTeX rules
the checks enforce first among them: cite only the bibliography's entries, a new entry only with its DOI or arXiv id, a
source or an UNVERIFIED mark on each value, compile clean, keep the document's style, answer each number."""

import json
from importlib import resources

from clank.components.agents.adapters.opencode import GUARDS, READING, OpenCode
from clank.components.agents.adapters.program import AgentModel
from clank.components.tools.service import Server

MODEL = AgentModel(url="http://edge:18210/v1", name="agent", title="daily 262K", context=262144, output=16384)
SERVER = Server("stdio", command="myproject-mcp")


def prompt(name: str) -> str:
    return resources.files("clank.components.agents").joinpath("prompts", name).read_text(encoding="utf-8")


def test_its_configuration_is_clanks_gateway_with_the_agent_role_and_its_limits() -> None:
    path, text = OpenCode().configuration(MODEL)
    assert path == "/home/agent/.config/opencode/opencode.json"
    config = json.loads(text)
    provider = config["provider"]["clank"]
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert provider["options"]["baseURL"] == "http://edge:18210/v1"
    model = provider["models"]["agent"]
    assert model["name"] == "daily 262K"
    assert model["limit"] == {"context": 262144, "output": 16384}
    assert (model["reasoning"], model["tool_call"]) == (True, True)
    assert model["interleaved"] == {"field": "reasoning_content"}
    assert (config["model"], config["small_model"], config["enabled_providers"]) == (
        "clank/agent",
        "clank/agent",
        ["clank"],
    )
    assert (config["autoupdate"], config["share"]) == (False, "disabled")
    assert config["permission"] == {
        "external_directory": "deny",
        "webfetch": "deny",
        "websearch": "deny",
        "edit": "ask",
    }, "it asks before every change to a file: Clank answers (design 0007 §3)"


def test_the_planner_writes_markdown_only_reads_freely_and_gets_only_the_tools_marked_read_only() -> None:
    servers = {"myproject": SERVER, "my.server": SERVER}
    read_only = {"myproject": ["estimate_run", "capabilities"], "my.server": ["look.up"]}
    config = json.loads(OpenCode().configuration(MODEL, servers, read_only)[1])
    assert config["agent"]["plan"] == {"disable": True}, "OpenCode's own planner, whose plan file is its own, is off"
    planner = config["agent"]["planner"]
    assert (planner["mode"], planner["prompt"]) == ("primary", prompt("planner.md"))
    assert "Markdown" in planner["description"]
    rules = planner["permission"]
    assert list(rules) == [
        "edit", "bash", "doom_loop", "question", "task",
        "my_server_*", "my_server_look_up",
        "myproject_*", "myproject_capabilities", "myproject_estimate_run",
    ], "the last rule that matches wins: each server's deny comes before its read-only tools"  # fmt: skip
    assert list(rules["edit"].items()) == [
        ("*", "deny"), ("*.md", "allow"),
        ("*.opencode/*", "deny"), ("*.claude/*", "deny"), ("*.git/*", "deny"), ("*.github/*", "deny"),
        ("*.vscode/*", "deny"), ("*AGENTS.md", "deny"), ("*CLAUDE.md", "deny"),
    ], "no settings or instructions another agent loads, and nothing outside Markdown"  # fmt: skip
    assert list(rules["bash"].items()) == [
        ("*", "deny"),
        *(rule for command in READING for rule in ((command, "allow"), (f"{command} *", "allow"))),
        *((guard, "deny") for guard in GUARDS),
    ], "a reading command redirected, substituted or writing a file is refused: the guards come last"
    assert READING == (
        "ls", "cat", "head", "tail", "wc", "grep", "echo", "pwd", "diff", "nl", "file", "stat", "du", "which",
        "git status", "git log", "git diff", "git show",
    )  # fmt: skip
    assert GUARDS == ("*>*", "*$(*", "*`*", "*--output*")
    assert rules["doom_loop"] == "deny", "a call repeated is refused, not asked about"
    assert (rules["question"], rules["task"]) == ("allow", {"*": "deny", "explore": "allow"})
    assert rules["myproject_*"] == "deny"
    assert config["permission"]["edit"] == "ask", "every other agent still asks before each change"


def test_the_planner_and_the_explore_helper_it_calls_never_ask_for_a_permission() -> None:
    config = json.loads(OpenCode().configuration(MODEL, {"myproject": SERVER}, {"myproject": ["capabilities"]})[1])

    def answers(rules: object) -> set[str]:
        return (
            {each for value in rules.values() for each in answers(value)} if isinstance(rules, dict) else {str(rules)}
        )

    assert answers(config["agent"]["planner"]["permission"]) == {"allow", "deny"}
    explore = config["agent"]["explore"]["permission"]
    assert answers(explore) == {"allow", "deny"}
    assert explore["bash"] == config["agent"]["planner"]["permission"]["bash"], "it reads as the planner does"
    assert (explore["edit"], explore["doom_loop"]) == ("deny", "deny")


def test_a_server_with_no_read_only_tools_known_gives_the_planner_none() -> None:
    config = json.loads(OpenCode().configuration(MODEL, {"notes": SERVER})[1])
    rules = config["agent"]["planner"]["permission"]
    assert [key for key in rules if key.startswith("notes")] == ["notes_*"]
    assert rules["notes_*"] == "deny"


def test_implement_hands_a_plan_to_build_with_its_instructions() -> None:
    command = json.loads(OpenCode().configuration(MODEL)[1])["command"]["implement"]
    assert (command["agent"], command["template"]) == ("build", prompt("implement.md"))
    assert "plan" in command["description"]
    assert "$ARGUMENTS" in command["template"]


def test_the_instructions_say_how_to_plan_measure_and_carry_out_a_plan() -> None:
    planner, implement = prompt("planner.md"), prompt("implement.md")
    sections = ["Question", "Parameters", "Cost", "Checks", "Plots", "Data", "Steps", "Open questions", "Log",
                "Deliverables"]  # fmt: skip
    found = [planner.index(f"- **{section}**") for section in sections]
    assert found == sorted(found), "the default layout's sections, in order, Deliverables last"
    for needed in ("kind: plan", "status: ready", "question tool", "benchmark", "estimate tool", "1 thread", "limit",
                   "estimated", "measured", "projected", "throughput", "embedded", "clank mcp check", "/implement",
                   "Never code", "never for a permission", "is refused", "estimate and benchmark tools",
                   "offset"):  # fmt: skip
        assert needed in planner, needed
    for needed in ("status: implementing", "- [x]", "Log", "Deliverables", "question tool", "more than half",
                   "status: done", "$ARGUMENTS"):  # fmt: skip
        assert needed in implement, needed


def test_every_agent_reads_clanks_instructions_in_the_container_the_latex_rules_among_them() -> None:
    from clank.components.workspaces.sandbox import image_folder

    config = json.loads(OpenCode().configuration(MODEL)[1])
    assert config["instructions"] == ["/opt/clank/instructions/*.md"]
    rules = (image_folder() / "instructions" / "latex.md").read_text(encoding="utf-8")
    for needed in ("Cite only entries", "doi = {", "archivePrefix = {arXiv}", "% source:", "% UNVERIFIED:",
                   "no undefined", "own macros", "answer each by its number", "refused"):  # fmt: skip
        assert needed in rules, needed
    dockerfile = (image_folder() / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY instructions/ /opt/clank/instructions/" in dockerfile


def test_it_runs_its_terminal_interface_offline() -> None:
    program = OpenCode()
    assert program.argv() == ["opencode"]
    assert program.env() == {
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
        "OPENCODE_DISABLE_SHARE": "1",
        "OPENCODE_DISABLE_CLAUDE_CODE": "1",
        "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "1",
    }
