"""Clank's figure geometry (design 0008 §3): when Matplotlib saves a raster figure inside the workspace's folder, write
what a mark drawn on the image needs to be said in the figure's own terms.

`install` (from the sandbox image's `sitecustomize`) waits for `matplotlib.figure` to be imported, then wraps
`Figure.savefig`: after a PNG or JPEG is saved under the folder (`CLANK_FIGURES_ROOT`, `/workspace` in a container),
`.clank/figures/<its path>.json` holds the image's size and checksum, and for each plot (axes) its box in the image's
pixels (left, top, right, bottom), its data limits and scales, its title and axis labels, its lines and scatters (label,
color, at most `POINTS` of their points; a line with error bars is one line) and its legend (entries, box); and the
figure's title. Positions are measured after the save, through the box the file was cut to (a tight one too). Nothing is
imported until Matplotlib is, and any failure is swallowed: Clank never makes a save fail.
"""

import contextlib
import functools
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import struct
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

POINTS = 400  # of a line's points kept
RASTER = {".png", ".jpg", ".jpeg"}


def install() -> None:
    """Wrap `Figure.savefig` once Matplotlib's figure module is imported (now, if it is already)."""
    if "matplotlib.figure" in sys.modules:
        _patch(sys.modules["matplotlib.figure"])
    else:
        sys.meta_path.insert(0, _Finder())


class _Finder(importlib.abc.MetaPathFinder):
    """Finds nothing itself: when `matplotlib.figure` is found, its loading is followed by the wrap."""

    def find_spec(self, name: str, path: Any = None, target: Any = None) -> importlib.machinery.ModuleSpec | None:
        if name != "matplotlib.figure":
            return None
        sys.meta_path.remove(self)
        spec = importlib.util.find_spec(name)
        loader = spec.loader if spec is not None else None
        if loader is None or not hasattr(loader, "exec_module"):
            return spec
        original = loader.exec_module

        def exec_module(module: ModuleType) -> None:
            original(module)
            with contextlib.suppress(Exception):
                _patch(module)

        loader.exec_module = exec_module  # type: ignore[method-assign]
        return spec


def _patch(module: ModuleType) -> None:
    figure = module.Figure
    original = figure.savefig
    if getattr(original, "_clank", False):
        return

    @functools.wraps(original)  # its name and documentation too: pyplot copies them
    def savefig(self: Any, fname: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, fname, *args, **kwargs)
        with contextlib.suppress(Exception):
            record(self, fname, kwargs)
        return result

    savefig._clank = True  # type: ignore[attr-defined]
    figure.savefig = savefig


def record(fig: Any, fname: Any, kwargs: dict[str, Any]) -> Path | None:
    """Write the geometry of a figure just saved as `fname`; where, or None when it is not one Clank keeps."""
    if not isinstance(fname, (str, os.PathLike)):
        return None
    path = Path(os.fspath(fname))
    given = kwargs.get("format")
    if not path.suffix and not given:
        path = path.with_suffix(".png")
    if (f".{given}".lower() if given else path.suffix.lower()) not in RASTER:
        return None
    root = Path(os.environ.get("CLANK_FIGURES_ROOT", "/workspace")).resolve()
    path = path.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    data = path.read_bytes()
    size = _size(data)
    if size is None:
        return None
    geometry = {
        "schema": "clank-figure/1",
        "image": relative.as_posix(),
        "size": list(size),
        "sha256": hashlib.sha256(data).hexdigest(),
        "made": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **_measure(fig, kwargs, size),
    }
    folder = root / ".clank" / "figures"
    kept = folder / f"{relative.as_posix()}.json"
    kept.parent.mkdir(parents=True, exist_ok=True)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    part = kept.with_name(kept.name + ".part")
    part.write_text(json.dumps(geometry, ensure_ascii=False), encoding="utf-8")
    part.replace(kept)
    return kept


def _measure(fig: Any, kwargs: dict[str, Any], size: tuple[int, int]) -> dict[str, Any]:
    """Each plot's place in the image and what it shows; the figure's title."""
    import matplotlib
    from matplotlib.transforms import Bbox

    renderer = fig.canvas.get_renderer()
    cut = kwargs.get("bbox_inches", matplotlib.rcParams["savefig.bbox"])
    pad = kwargs.get("pad_inches", matplotlib.rcParams["savefig.pad_inches"])
    if cut == "tight":
        box = fig.get_tightbbox(renderer).padded(pad if isinstance(pad, (int, float)) else 0.1)
    elif isinstance(cut, Bbox):
        box = cut
    else:
        box = fig.bbox_inches
    per_x, per_y = size[0] / box.width, size[1] / box.height

    def place(extent: Any) -> list[float]:
        """A display box (pixels at the figure's own dots per inch) in the image's pixels: left, top, right, bottom."""
        inches = extent.transformed(fig.dpi_scale_trans.inverted())
        return [
            round((inches.x0 - box.x0) * per_x, 1), round((box.y1 - inches.y1) * per_y, 1),
            round((inches.x1 - box.x0) * per_x, 1), round((box.y1 - inches.y0) * per_y, 1),
        ]  # fmt: skip

    plots = []
    for index, ax in enumerate(fig.axes):
        legend = ax.get_legend()
        plots.append({
            "index": index,
            "box": place(ax.get_window_extent(renderer)),
            "title": ax.get_title() or ax.get_title("left") or ax.get_title("right"),
            "xlabel": ax.get_xlabel(), "ylabel": ax.get_ylabel(),
            "xlim": [float(value) for value in ax.get_xlim()], "ylim": [float(value) for value in ax.get_ylim()],
            "xscale": ax.get_xscale(), "yscale": ax.get_yscale(),
            "colorbar": hasattr(ax, "_colorbar"),
            "lines": _lines(ax),
            "scatters": [found for found in (_scatter(each) for each in ax.collections) if found is not None],
            "legend": {"entries": [text.get_text() for text in legend.get_texts()],
                       "box": place(legend.get_window_extent(renderer))} if legend is not None else None,
            "labels": {
                name: place(text.get_window_extent(renderer))
                for name, text in (("title", ax.title), ("xlabel", ax.xaxis.label), ("ylabel", ax.yaxis.label))
                if text.get_text()
            },
        })  # fmt: skip
    title = fig._suptitle.get_text() if getattr(fig, "_suptitle", None) is not None else ""
    return {"dpi": round(per_x, 2), "title": title, "axes": plots}


def _label(artist: Any) -> str:
    label = str(artist.get_label() or "")
    return "" if label.startswith("_") else label


def _numbers(values: Any) -> list[float] | None:
    try:
        found = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if len(found) > POINTS:
        step = len(found) / POINTS
        found = [found[int(index * step)] for index in range(POINTS)]
    return [round(value, 6) if value == value else value for value in found]


def _lines(ax: Any) -> list[dict[str, Any]]:
    """A plot's lines; a line with error bars is its data line, named as its legend names it (its caps are none)."""
    from matplotlib.container import ErrorbarContainer

    named: dict[int, str] = {}
    caps: set[int] = set()
    for container in ax.containers:
        if isinstance(container, ErrorbarContainer):
            data, capped, _ = container.lines
            if data is not None:
                named[id(data)] = _label(container)
            caps.update(id(each) for each in capped)
    found = (_line(each, named.get(id(each))) for each in ax.get_lines() if id(each) not in caps)
    return [line for line in found if line is not None]


def _line(line: Any, label: str | None = None) -> dict[str, Any] | None:
    from matplotlib.colors import to_hex

    xs, ys = _numbers(line.get_xdata()), _numbers(line.get_ydata())
    if xs is None or ys is None:
        return None
    return {"label": _label(line) if label is None else label, "color": to_hex(line.get_color()),
            "points": len(line.get_xdata()), "x": xs, "y": ys}  # fmt: skip


def _scatter(collection: Any) -> dict[str, Any] | None:
    from matplotlib.collections import PathCollection
    from matplotlib.colors import to_hex

    if not isinstance(collection, PathCollection):
        return None
    offsets: Any = collection.get_offsets()
    colors: Any = collection.get_facecolor()
    xs, ys = _numbers(offsets[:, 0]), _numbers(offsets[:, 1])
    if xs is None or ys is None:
        return None
    return {"label": _label(collection), "color": to_hex(colors[0]) if len(colors) else "", "points": len(offsets),
            "x": xs, "y": ys}  # fmt: skip


def _size(data: bytes) -> tuple[int, int] | None:
    """A PNG's or a JPEG's width and height, from its header."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    if data[:2] == b"\xff\xd8":
        at = 2
        while at + 9 < len(data):
            if data[at] != 0xFF:
                return None
            marker = data[at + 1]
            length = struct.unpack(">H", data[at + 2 : at + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack(">HH", data[at + 5 : at + 9])
                return width, height
            at += 2 + length
    return None
