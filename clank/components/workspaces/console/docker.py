"""Docker's page in the console (design 0002 §3.2): its state and versions, a one-line summary, and every container
with whose it is (Clank's or another program's), running ones first. `s` starts or stops Docker (stopping
asks first when containers Clank did not start run, and the question appears on the home and questions pages); `r`
reads Docker again now instead of at the next check. Its two panels, "Docker" and "Containers", are board E5's
(design 0011 §8).
"""

from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.components.workspaces.service import image_name
from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.style import mark
from clank.console.text import painted, time_of, tone

OWNERS = {"clank": "Clank's", "other": "other"}


def containers_text(containers: list[dict[str, Any]]) -> str:
    """Every container in columns, running ones first."""
    if not containers:
        return "No container."
    ordered = sorted(containers, key=lambda container: (container["state"] != "running", container["name"]))
    width = max(len("NAME"), *(len(container["name"]) for container in ordered))
    head = f"{'NAME':<{width}}  {'WHOSE':<9}  {'STATE':<8}  {'STATUS':<24}  IMAGE"
    rows = [
        f"{c['name']:<{width}}  {OWNERS[c['owner']]:<9}  {c['state']:<8}  {c['status'][:24]:<24}  "
        + image_name(c["image"])
        for c in ordered
    ]
    return "\n".join([head, *rows])


def containers_in_color(containers: list[dict[str, Any]]) -> Content:
    """The containers' table with its head in bold and each container's state in its color."""
    head, *rows = containers_text(containers).split("\n")
    if not rows:
        return Content(head)
    ordered = sorted(containers, key=lambda container: (container["state"] != "running", container["name"]))
    lines = [
        Content.assemble((head, "bold")),
        *(painted(row, c["state"]) for row, c in zip(rows, ordered, strict=True)),
    ]
    return Content("\n").join(lines)


class DockerPage(Page):
    """Docker, and whose each container is."""

    ENTRY = MenuEntry(
        "docker",
        "Docker",
        "Docker's state, its containers and whose each one is; s starts or stops it.",
        "design 0002 §3.2",
        key="4",
    )
    PANELS = ("docker-state-panel", "docker-containers-panel")
    KEYS = (
        PageKey("s", "docker", "start or stop Docker"),
        PageKey("r", "read", "read it again"),
    )

    def badge(self, frame: int) -> Content | None:
        """A dot in Docker's state's color."""
        docker = self.console.data.docker
        return Content.assemble((mark("on"), tone(docker["state"]) or "$clank-quiet")) if docker else None

    def compose(self) -> ComposeResult:
        """Docker's state, then its containers."""
        with Panel(title="Docker", id="docker-state-panel"):
            yield Label(id="docker-state")
        with Panel(title="Containers", id="docker-containers-panel"):
            yield Label(id="docker-containers")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw Docker again when it changed."""
        if not changed & {"all", "docker"}:
            return
        docker = data.docker
        if docker is None:
            self.query_one("#docker-state", Label).update("Not read yet.")
            self.query_one("#docker-containers", Label).update("")
            return
        head = f"{docker['label']} {docker['version']}".strip() + f" · {docker['state']}"
        lines = [head + (f" · engine {docker['engine']}" if docker["engine"] else "")]
        lines.append(docker["summary"].split(" · ", 2)[-1] if docker["state"] == "running" else docker["detail"])
        key = "s stops it" if docker["state"] == "running" else "s starts it"
        lines.append(f"read {time_of(docker['checked'], self.console.zone)}   ({key} · r reads it again)")
        shown = [painted(line, docker["state"]) for line in lines if line]
        self.query_one("#docker-state", Label).update(Content("\n").join(shown))
        self.query_one("#docker-containers", Label).update(containers_in_color(docker["containers"]))

    def press(self, key: str) -> bool:
        """`s` starts or stops Docker; `r` reads it again."""
        console = self.console
        docker, client = console.data.docker, console.client
        if key == "s" and docker:
            console.ask_docker(docker["state"] == "running")
            return True
        if key == "r":
            actions.call(console, lambda: client.get("docker", refresh=True), done="read Docker again")
            return True
        return False

    def explain(self) -> tuple[str, list[str]]:
        """Whose a container is, and what Clank may do with Docker."""
        return "Docker", [
            "A container is Clank's when its clank.home label is this CLANK_HOME's id; otherwise another program's.",
            "Clank acts on Docker only as a whole, and stopping it stops every container in it, so it asks first "
            "whenever a container it did not start is running, naming each (design 0001 §4.6, design 0002 §3.2).",
            "Docker is read every few seconds (config/docker.json: poll_seconds), through its adapter, Docker "
            "Desktop first (design 0002 §2.9, §2.10).",
        ]
