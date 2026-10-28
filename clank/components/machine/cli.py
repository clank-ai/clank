"""The machine component's command: `clank doctor`, which checks this computer and changes nothing.

It is one of the three commands that act without a running service (design 0002 §2.15): it detects the machine and
runs the checks itself, reading Docker through the platform the settings choose (design 0014 §2). It exits with 1 when
a check failed (a warning is not a failure).
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from clank.components.machine.checks import MARKS, Facts, free_gb, hags_mode, run_checks
from clank.components.machine.detect import detect
from clank.components.workspaces.service import read_platform
from clank.kernel.home import Home
from clank.kernel.processes import run_command


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def doctor(as_json: bool) -> None:
    """Check this computer for what Clank needs (read only: it changes nothing)."""
    home = Home.resolve()
    profile = detect(run_command)
    facts = Facts(
        home=home, profile=profile, docker=read_platform(home), port=_port(home), hags_mode=hags_mode(),
        free_gb=free_gb(home), more=_declared(),
    )  # fmt: skip
    results = run_checks(facts)
    if as_json:
        report = {"profile": profile.model_dump(mode="json"), "checks": [asdict(result) for result in results]}
        click.echo(json.dumps(report, indent=2))
    else:
        gpus = ", ".join(f"{gpu.name} {gpu.memory_mib / 1024:.0f} GB" for gpu in profile.gpus) or "no NVIDIA GPU"
        click.echo(
            f"Machine: {profile.system} · {profile.processor} ({profile.cores} cores) · {profile.memory_gb:.0f} GB "
            f"· {gpus} · Python {profile.python}" + (f" · {profile.wsl}" if profile.wsl else "")
        )
        width = max(len(result.title) for result in results)
        for result in results:
            click.echo(f"  {MARKS[result.status]}  {result.title.ljust(width)}  {result.detail}")
            if result.fix:
                click.echo(f"        {' ' * width}  -> {result.fix}")
        passed = sum(1 for result in results if result.status == "passed")
        warnings = sum(1 for result in results if result.status == "warning")
        click.echo(f"{passed} of {len(results)} checks passed" + (f", {warnings} warning(s)" if warnings else ""))
    if any(result.status == "failed" for result in results):
        raise SystemExit(1)


def _declared() -> tuple[Any, ...]:
    """The doctor checks the components declare (design 0002 §2.1): the phone's way in among them."""
    from clank import registry

    return tuple(component.checks for component in registry.components() if component.checks is not None)


def _port(home: Home) -> int:
    path: Path = home.config / "service.json"
    try:
        return int(json.loads(path.read_text(encoding="utf-8-sig")).get("port", 7720))
    except (OSError, ValueError, AttributeError):
        return 7720
