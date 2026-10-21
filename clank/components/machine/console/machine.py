"""The machine's page in the console (design 0001 §2, §7.3): this computer as Clank last detected it, and the doctor's
last checks, each with what to do when it did not pass. `d` runs the doctor, which detects the machine again; its
steps show on the operations page and its result here when it ends. Its two panels, "Profile" and "Doctor", are board
E6's (design 0011 §8).
"""

from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.components.machine.checks import MARKS
from clank.console.data import ConsoleData
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.text import time_of

MARK_TONES = {"ok": "$clank-good", "warn": "$clank-attention", "FAIL": "$clank-failed", "skip": "$clank-quiet"}


def profile_text(profile: dict[str, Any], zone: Any) -> str:
    """The machine profile, one fact a line."""
    if not profile.get("detected"):
        return "Not detected yet: d runs the doctor, which detects it."
    gpus = [f"{gpu['name']}, {gpu['memory_mib'] / 1024:.0f} GB, driver {gpu['driver']}" for gpu in profile["gpus"]]
    facts = [
        ("system", profile["system"]),
        ("python", profile["python"]),
        ("wsl", profile["wsl"] or "(only on Windows)"),
        ("processor", f"{profile['processor']}, {profile['cores']} cores"),
        ("memory", f"{profile['memory_gb']:.0f} GB"),
        ("gpus", "; ".join(gpus) or "no NVIDIA GPU"),
        ("docker", profile["docker"]),
        ("detected", time_of(profile["detected"], zone)),
    ]
    return "\n".join(f"{name:<10} {value}" for name, value in facts)


def doctor_in_color(text: str) -> Content:
    """The doctor's checks with each mark in its color: ok green, warn yellow, FAIL red, skip muted."""
    lines = []
    for line in text.split("\n"):
        mark = line[:4].strip()
        shown = Content(line)
        lines.append(shown.stylize(MARK_TONES[mark], 0, len(mark)) if mark in MARK_TONES else shown)
    return Content("\n").join(lines)


def doctor_text(doctor: dict[str, Any] | None) -> str:
    """The doctor's last checks, each with what to do when it did not pass."""
    if doctor is None:
        return "The doctor has not run yet: d runs it."
    width = max(len(check["title"]) for check in doctor["checks"])
    lines = [f"{doctor['passed']} of {doctor['of']} passed   (d runs it again)"]
    for check in doctor["checks"]:
        lines.append(f"{MARKS[check['status']]}  {check['title']:<{width}}  {check['detail']}")
        if check["fix"]:
            lines.append(f"      {'':<{width}}  {check['fix']}")
    return "\n".join(lines)


class MachinePage(Page):
    """This computer, and the doctor's checks."""

    ENTRY = MenuEntry(
        "machine",
        "Machine",
        "This computer as Clank sees it, and the doctor's checks with what to do; d runs the doctor.",
        "design 0001 §2, §7.3",
        key="5",
    )
    PANELS = ("machine-profile-panel", "machine-doctor-panel")
    KEYS = (PageKey("d", "doctor", "run the doctor"),)

    def compose(self) -> ComposeResult:
        """The profile, then the doctor's checks."""
        with Panel(title="Profile", id="machine-profile-panel"):
            yield Label(id="machine-profile")
        with Panel(title="Doctor", id="machine-doctor-panel"):
            yield Label(id="machine-doctor")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the machine again when it changed."""
        if not changed & {"all", "machine"} or data.machine is None:
            return
        self.query_one("#machine-profile", Label).update(profile_text(data.machine["profile"], self.console.zone))
        self.query_one("#machine-doctor", Label).update(doctor_in_color(doctor_text(data.machine["doctor"])))

    def press(self, key: str) -> bool:
        """`d` runs the doctor."""
        if key != "d":
            return False
        self.console.run_doctor()
        return True

    def explain(self) -> tuple[str, list[str]]:
        """Where the profile and the checks come from."""
        return "Machine", [
            "The profile is config/machine.json, written by the doctor each time it detects the machine; a value it "
            "got wrong can be corrected there.",
            "The checks are those of `clank doctor`: what Clank needs from this computer, each with what to do when "
            "it did not pass. None of them changes anything (design 0001 §4.7).",
            "Designed in design 0001 §2 and §7.3.",
        ]
