"""Design 0009 §4: a plan is a Markdown file whose header (its front matter, between a first line `---` and the next
`---`) says `kind: plan`, wherever it lives in the folder; a file that only mentions it elsewhere is not one, and no
file is a plan outside the folder, in a folder agents and assistants load their settings from, or among the files
that instruct them (`AGENTS.md`, `CLAUDE.md`)."""

import pytest

from clank.components.agents.plans import is_plan, plan_path


@pytest.mark.parametrize(
    "text",
    [
        "---\nkind: plan\n---\n# A study\n",
        "---\ntitle: Walk scan\nkind: plan\nstatus: draft\n---\n\n## Question\n",
        "---\r\nkind: plan\r\nstatus: ready\r\n---\r\n# On Windows\r\n",
        "---\nkind:   plan  \n---\n",
        "---\nkind: plan\n---",
        "--- \nkind: plan\n---  \n",
    ],
)
def test_a_header_that_says_kind_plan_makes_a_plan(text: str) -> None:
    assert is_plan(text)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "# Notes\n\nkind: plan\n",
        "---\nkind: plan\n# the header never closes\n",
        "---\nkind: plans\n---\n",
        "---\nkind: study\n---\n",
        "---\ntitle: x\n---\n\n---\nkind: plan\n---\n",
        "\n---\nkind: plan\n---\n",
        "----\nkind: plan\n----\n",
    ],
)
def test_anything_else_is_not_a_plan(text: str | None) -> None:
    assert not is_plan(text)


@pytest.mark.parametrize("relative", ["plan.md", "studies/2026-10-20-sweep/plan.md", "notes/Draft.MD"])
def test_a_markdown_file_in_the_folder_may_be_a_plan(relative: str) -> None:
    assert plan_path(relative)


@pytest.mark.parametrize(
    "relative",
    [
        "a.py",
        "x.yml",
        "plan.md.py",
        ".opencode/agent/helper.md",
        "sub/.opencode/command/go.md",
        ".claude/skills/s/SKILL.md",
        ".git/description.md",
        ".github/pull_request_template.md",
        "AGENTS.md",
        "docs/CLAUDE.md",
        "agents.md",
        "../outside.md",
        "studies/../../outside.md",
        "/etc/notes.md",
        "D:/other/plan.md",
        "D:plan.md",
        "c:/notes/plan.md",
        "",
    ],
)
def test_no_other_file_is_one(relative: str) -> None:
    assert not plan_path(relative)
