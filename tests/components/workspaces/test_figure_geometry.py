"""Design 0008 §3: when Matplotlib saves a raster figure inside the workspace's folder, the sandbox's `sitecustomize`
writes its geometry under `.clank/figures/` (a `.gitignore` keeps git out): the image's size and checksum, each plot's
box in the image's pixels, its data limits and scales, its title and labels, its lines with their labels and data, its
legend. A point of the data, placed through that geometry, falls on the pixel Matplotlib drew it on, with a tight
bounding box and on a log scale too. A figure saved outside the folder, or as a PDF, gets none; a Python that never
imports Matplotlib never loads it."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib.image

from clank.components.workspaces.sandbox import image_folder
from clank.kernel.processes import background_flags

HOOK = image_folder() / "python"
SCRIPT = """
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, (left, right) = plt.subplots(1, 2, figsize=(8, 3.5))
left.plot([0, 1, 2, 3, 4], [0, 1, 4, 9, 16], color="#1f77b4", label="n = 16")
left.plot([2.5], [3.0], "o", color="#ff0000", markersize=14, label="_dot")
left.set(title="MSD vs time", xlabel="time", ylabel="MSD")
left.legend(loc="upper left")
right.semilogy([1, 2, 3, 4], [10, 100, 1000, 10000], color="#9467bd", label="growth")
right.semilogy([2.5], [300.0], "s", color="#00aa00", markersize=14, label="_square")
right.set_title("growth")
fig.savefig("figs/plot.png", dpi=100, bbox_inches="tight")
fig.savefig("figs/plot.pdf")
fig.savefig(sys.argv[1] + "/outside.png")
"""


def run(folder: Path, *argv: str, code: str = SCRIPT) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(HOOK), "CLANK_FIGURES_ROOT": str(folder), "MPLBACKEND": "Agg"}
    return subprocess.run(
        [sys.executable, "-c", code, *argv], cwd=folder, env=env, capture_output=True, text=True, timeout=120,
        creationflags=background_flags(),
    )  # fmt: skip


def pixel(geometry: dict[str, Any], axes: int, x: float, y: float) -> tuple[int, int]:
    """Where a data point falls in the image, through the geometry (log axes in their own scale)."""
    plot = geometry["axes"][axes]
    left, top, right, bottom = plot["box"]

    def fraction(value: float, limits: list[float], scale: str) -> float:
        low, high = limits
        if scale == "log":
            import math

            return (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low))
        return (value - low) / (high - low)

    across = fraction(x, plot["xlim"], plot["xscale"])
    up = fraction(y, plot["ylim"], plot["yscale"])
    return round(left + across * (right - left)), round(bottom - up * (bottom - top))


def test_a_saved_figure_has_its_geometry_and_a_data_point_falls_where_matplotlib_drew_it(tmp_path: Path) -> None:
    folder, outside = tmp_path / "paper", tmp_path / "elsewhere"
    (folder / "figs").mkdir(parents=True)
    outside.mkdir()
    done = run(folder, str(outside))
    assert done.returncode == 0, done.stderr
    kept = folder / ".clank" / "figures" / "figs" / "plot.png.json"
    geometry = json.loads(kept.read_text(encoding="utf-8"))
    assert (folder / ".clank" / "figures" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    image = matplotlib.image.imread(folder / "figs" / "plot.png")
    assert geometry["size"] == [image.shape[1], image.shape[0]]
    assert geometry["image"] == "figs/plot.png"
    left, right = geometry["axes"]
    assert (left["title"], left["xlabel"], left["ylabel"], left["xscale"]) == ("MSD vs time", "time", "MSD", "linear")
    assert [line["label"] for line in left["lines"]] == ["n = 16", ""]
    assert left["lines"][0]["y"] == [0, 1, 4, 9, 16]
    assert left["legend"]["entries"] == ["n = 16"]
    assert (right["title"], right["yscale"]) == ("growth", "log")
    red = image[pixel(geometry, 0, 2.5, 3.0)[::-1]]
    assert (red[0] > 0.8, red[1] < 0.3, red[2] < 0.3) == (True, True, True), f"the red dot is not there: {red}"
    green = image[pixel(geometry, 1, 2.5, 300.0)[::-1]]
    assert (green[0] < 0.3, green[1] > 0.5, green[2] < 0.3) == (True, True, True), (
        f"the green square is not there: {green}"
    )
    assert not (folder / ".clank" / "figures" / "figs" / "plot.pdf.json").exists(), "only raster figures"
    assert not list(outside.rglob("*.json")), "nothing for a figure outside the folder"


def test_a_line_with_error_bars_is_one_line_named_as_its_legend_names_it(tmp_path: Path) -> None:
    code = """
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
for n, shift in ((16, 0.0), (32, 1.0)):
    ax.errorbar([0.1, 0.2, 0.3], [shift + 1, shift + 2, shift + 3], yerr=[0.1, 0.1, 0.1], capsize=3, label=f"n = {n}")
ax.legend()
fig.savefig("bars.png")
"""
    done = run(tmp_path, code=code)
    assert done.returncode == 0, done.stderr
    geometry = json.loads((tmp_path / ".clank" / "figures" / "bars.png.json").read_text(encoding="utf-8"))
    lines = geometry["axes"][0]["lines"]
    assert [(line["label"], line["y"]) for line in lines] == [("n = 16", [1, 2, 3]), ("n = 32", [2, 3, 4])]


def test_a_python_that_never_imports_matplotlib_never_loads_it(tmp_path: Path) -> None:
    done = run(tmp_path, code="import sys; print('matplotlib' in sys.modules, 'sitecustomize' in sys.modules)")
    assert done.stdout.split() == ["False", "True"]
