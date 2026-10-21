"""Clank's sitecustomize in the sandbox image (design 0008 §3): every Python in a workspace's container finds it on
`PYTHONPATH` and loads it at start. It only arranges for Matplotlib's saved figures to have their geometry written
(`clank_figures`), which happens when, and only if, Matplotlib is imported; then it runs the next `sitecustomize` on
the path, if there is one (a virtual environment's own), as Python would have."""

import contextlib
import importlib.util
import os
import sys

with contextlib.suppress(Exception):
    # Beside this file on PYTHONPATH in the image, so Python finds it there; Clank's own checks do not.
    import clank_figures  # type: ignore[import-not-found]

    clank_figures.install()

with contextlib.suppress(Exception):
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in sys.path:
        if folder and os.path.abspath(folder) != here and os.path.isfile(os.path.join(folder, "sitecustomize.py")):
            spec = importlib.util.spec_from_file_location(
                "_next_sitecustomize", os.path.join(folder, "sitecustomize.py")
            )
            if spec is not None and spec.loader is not None:
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
            break
