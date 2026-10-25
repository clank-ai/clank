"""Design 0018 §7.4: Clank's own MCP server gives the agent `find_figures(query, limit)`, which finds the figures of
the folder that best match words, from what is known of each: its name and folder; the title, axis labels and legend
Matplotlib recorded when it was saved (`.clank/figures/`) and the script that saved it; the LaTeX `\\caption` and
`\\label` of a figure environment that includes it; a script that names it; and when it was made (today, yesterday,
this week, last week, a weekday, the latest). Each figure found says why it matched. Folders of tools and environments
(`.git`, `node_modules`, `.venv`, caches) are not searched. It runs in the container, reads only, asks nothing of the
gateway, and says when nothing matches, naming the newest figures instead."""

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from tests.components.agents.test_flow_tools import called, session

GATEWAY = "http://127.0.0.1:9/v1"  # never asked
DAY = 86400.0


def make(folder: Path, relative: str, data: bytes = b"\x89PNG\r\n\x1a\n", age_days: float = 3.0) -> Path:
    path = folder.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    moment = time.time() - age_days * DAY
    os.utime(path, (moment, moment))
    return path


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A folder with a recorded Matplotlib figure, a PDF figure in the paper, others, and folders not searched."""
    root = tmp_path / "work"
    make(root, "plots/residual.png", age_days=1.0)
    geometry = {
        "schema": "clank-figure/1", "image": "plots/residual.png", "title": "", "script": "analysis/converge.py",
        "axes": [{"index": 0, "title": "Residual vs iterations", "xlabel": "iteration", "ylabel": "residual",
                  "lines": [{"label": "warm start"}, {"label": "cold start"}], "scatters": [],
                  "legend": {"entries": ["warm start", "cold start"]}}],
    }  # fmt: skip
    kept = root / ".clank" / "figures" / "plots" / "residual.png.json"
    kept.parent.mkdir(parents=True)
    kept.write_text(json.dumps(geometry), encoding="utf-8")
    make(root, "figs/phase_diagram.pdf", b"%PDF-1.7\n", age_days=10.0)
    (root / "paper").mkdir()
    (root / "paper" / "main.tex").write_text(
        "\\begin{figure}\n  \\centering\n  \\includegraphics[width=\\linewidth]{../figs/phase_diagram}\n"
        "  \\caption{Phase diagram of the model as the coupling varies.}\n  \\label{fig:phases}\n\\end{figure}\n",
        encoding="utf-8",
    )
    (root / "scripts").mkdir()
    (root / "scripts" / "make_phase.py").write_text('plt.savefig("figs/phase_diagram.pdf")\n', encoding="utf-8")
    make(root, "images/logo.svg", b"<svg/>", age_days=30.0)
    make(root, "notes/sketch.jpg", age_days=0.01)
    make(root, ".git/objects/residual.png")
    make(root, "node_modules/pkg/residual.png")
    make(root, ".venv/lib/residual.png")
    return root


def found(folder: Path, arguments: dict[str, Any]) -> str:
    [reply] = session(folder, GATEWAY, [called("find_figures", arguments)])
    assert reply["result"]["isError"] is False, reply
    text: str = reply["result"]["content"][0]["text"]
    return text


def test_find_figures_is_listed_read_only_with_a_query_and_a_limit(folder: Path) -> None:
    [listed] = session(folder, GATEWAY, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    find = tools["find_figures"]
    assert find["annotations"]["readOnlyHint"] is True
    assert find["inputSchema"]["required"] == ["query"]
    assert set(find["inputSchema"]["properties"]) == {"query", "limit"}
    assert "show_files" in find["description"], "it says what to do with what it finds"
    assert "Returns" in find["description"]


def test_a_recorded_figure_is_found_by_its_title_labels_and_legend_with_why(folder: Path) -> None:
    text = found(folder, {"query": "warm and cold convergence of the residual"})
    first = text.splitlines()[0]
    assert first.startswith("1. plots/residual.png")
    assert "title 'Residual vs iterations'" in text
    assert "legend 'warm start', 'cold start'" in text
    assert "made by analysis/converge.py" in text
    for skipped in (".git", "node_modules", ".venv"):
        assert skipped not in text, "tools' folders are not searched"


def test_a_pdf_figure_is_found_by_its_latex_caption_and_the_script_that_names_it(folder: Path) -> None:
    text = found(folder, {"query": "phase diagram coupling"})
    assert text.splitlines()[0].startswith("1. figs/phase_diagram.pdf")
    assert "caption 'Phase diagram of the model as the coupling varies.' (paper/main.tex, fig:phases)" in text
    assert "named in scripts/make_phase.py" in text


def test_when_it_was_made_counts_and_the_limit_caps_the_list(folder: Path) -> None:
    text = found(folder, {"query": "the figure from yesterday"})
    assert text.splitlines()[0].startswith("1. plots/residual.png"), "made a day ago"
    latest = found(folder, {"query": "latest", "limit": 1})
    assert latest.splitlines()[0].startswith("1. notes/sketch.jpg")
    assert "2. " not in latest


def test_nothing_matching_says_so_and_names_the_newest_figures(folder: Path) -> None:
    text = found(folder, {"query": "spectral density of the bath"})
    assert text.startswith("No figure of the folder matches 'spectral density of the bath'.")
    assert "The newest: notes/sketch.jpg, plots/residual.png, figs/phase_diagram.pdf" in text
    assert list((folder / ".clank").iterdir()) == [folder / ".clank" / "figures"], "it writes nothing"
