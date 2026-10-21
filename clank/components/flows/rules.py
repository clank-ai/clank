"""The rules of a flow's file (design 0013 §2-§4, decision 0057), checked whenever a flow is read or written.

Each problem comes with its place in the file (`lines.3.to`), so the settings files name its line and field.

The flow starts with a YOU; boxes have ids of their own; a box done by the owner (YOU, GATE) names no model and no
mode; a line names boxes of the flow; only a VERIFY's lines say pass or fail, and a VERIFY has both, its pass line
leading on and its fail line back to the box it checks, which comes before it (so a flow never ends with a VERIFY); no
other line points back; a box goes on to one box and is reached by one line, but for a DECOMPOSE's tasks (TASK boxes),
which fan out from it, run one after another in the order of `boxes`, and join at the box after them; every box is
reached; a box in Plan mode writes only Markdown (the planner may not write another file); and every
file a box writes, sees or shows is named from the folder. The checks that need other records (the presets, the
workspace) are the component's (`clank.components.flows.service`).
"""

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clank.components.flows.kinds import Box, Flow, Line, Mode

BY_YOU = ("you", "gate")
PLAN_BY_DEFAULT = ("plan", "verify", "decompose", "integrate")
DRIVE = re.compile(r"^[A-Za-z]:")
Place = tuple[str | int, ...]


def in_the_folder(path: str) -> str:
    """A file of the workspace's folder, named from the folder with `/` (the folder is `/workspace` in the container and
    a Windows path on the host); anything else is refused as outside it."""
    example = "name it from the folder, as in runs/estimates.md"
    if not path.strip():
        raise ValueError(f"is empty: {example}")
    if "\\" in path:
        raise ValueError(f"{path} is written with '\\': {example}, '/' between folders")
    if path.startswith(("/", "~")) or DRIVE.match(path):
        raise ValueError(f"{path} is not in the folder: {example}")
    if ".." in path.split("/"):
        raise ValueError(f"{path} climbs out of the folder ('..'): a box reads and writes the folder's files only")
    return path


def effective_mode(box: "Box") -> "Mode | None":
    """The mode a box's session runs in: its own, else Plan for PLAN, VERIFY, DECOMPOSE and INTEGRATE; None for a TASK
    (the workspace's) and for the owner's boxes."""
    if box.mode is not None:
        return box.mode
    return "plan" if box.type in PLAN_BY_DEFAULT else None


def on_its_own(box: dict[str, Any]) -> bool:
    """A box of a flow built with the model, as its values say it (design 0013 §15, decision 0098): give it the mode
    auto when it changes files in a mode that would make each change wait for the owner (no mode, the workspace's, for
    a TASK; review); True when it was given auto. The owner's boxes and those in Plan mode stay as they are."""
    kind, mode = str(box.get("type") or ""), box.get("mode")
    if kind in BY_YOU or mode == "plan" or mode == "auto" or (mode is None and kind in PLAN_BY_DEFAULT):
        return False
    box["mode"] = "auto"
    return True


def rule_problems(flow: "Flow") -> list[tuple[Place, str]]:
    """Each place where the flow breaks a rule of design 0013 §3, with what is wrong, in the order of the file."""
    return sorted(_box_problems(flow) + _Graph(flow).problems(), key=lambda problem: _order(problem[0]))


def _box_problems(flow: "Flow") -> list[tuple[Place, str]]:
    found: list[tuple[Place, str]] = []
    ids = {box.id for box in flow.boxes}
    seen: set[str] = set()
    first = flow.boxes[0]
    if first.type != "you":
        found.append(
            (("boxes", 0, "type"), f"a flow starts with your brief: its first box is a YOU, not {_tag(first)}")
        )
    for i, box in enumerate(flow.boxes):
        if box.id in seen:
            found.append((("boxes", i, "id"), f"{box.id} is the id of an earlier box: each box has its own"))
        seen.add(box.id)
        if box.type in BY_YOU:
            for field in ("model", "mode"):
                if getattr(box, field):
                    found.append((("boxes", i, field), f"{_tag(box)} is done by you: it has no {field}"))
        if box.type == "verify" and not box.checks:
            found.append((("boxes", i, "checks"), "a VERIFY names the box whose deliverable it checks"))
        if box.type != "verify" and box.checks:
            found.append((("boxes", i, "checks"), f"only a VERIFY checks a box; {box.id} is {_tag(box)}"))
        if effective_mode(box) == "plan":
            for k, path in enumerate(box.writes):
                if not path.lower().endswith(".md"):
                    found.append(
                        (
                            ("boxes", i, "writes", k),
                            f"{path} is not Markdown, and {box.id} runs in Plan mode, whose planner writes Markdown "
                            "only: give it the mode review or auto",
                        )
                    )
        if box.proposed is not None and box.proposed.by not in ids:
            found.append((("boxes", i, "proposed", "by"), f"names no box of the flow: {box.proposed.by}"))
    return found


class _Graph:
    """The flow's lines, read once: which lead on (then and pass), which lead back (fail), which point back."""

    def __init__(self, flow: "Flow") -> None:
        self.flow = flow
        self.boxes = {box.id: box for box in reversed(flow.boxes)}  # an id used twice is its first box
        self.found: list[tuple[Place, str]] = []
        self.on: list[tuple[int, Line]] = []
        self.fails: list[tuple[int, Line]] = []
        for i, line in enumerate(flow.lines):
            missing = [end for end, name in (("from", line.from_), ("to", line.to)) if name not in self.boxes]
            for end in missing:
                name = line.from_ if end == "from" else line.to
                self.found.append((("lines", i, end), f"names no box of the flow: {name}"))
            if missing:
                continue
            source = self.boxes[line.from_]
            if source.type == "verify" and line.when is None:
                self.found.append((("lines", i, "when"), "a VERIFY's line says when it is taken: pass or fail"))
            if source.type != "verify" and line.when is not None:
                self.found.append(
                    (("lines", i, "when"), f"only a VERIFY's lines say pass or fail; {source.id} is {_tag(source)}")
                )
            (self.fails if source.type == "verify" and line.when == "fail" else self.on).append((i, line))
        self.back = self._back()
        self.ahead = [(i, line) for i, line in self.on if i not in self.back]

    def problems(self) -> list[tuple[Place, str]]:
        """Every problem of the lines, then of the boxes they leave unreached."""
        for i, line in self.on:
            if i in self.back:
                where = "the box it leaves" if line.to == line.from_ else f"{line.to}, which comes before {line.from_}"
                self.found.append(
                    (("lines", i, "to"), f"leads back to {where}: only a VERIFY's fail line may point back")
                )
        self._fans_and_joins()
        self._fail_lines()
        self._verify_lines()
        self._checks()
        reached = self._reached()
        for i, box in enumerate(self.flow.boxes):
            if box.id not in reached:
                self.found.append((("boxes", i, "id"), "no line reaches it: join it to the box before it"))
        return self.found

    def _back(self) -> set[int]:
        """The lines leading on that point back: to a box on the path that leads to their own (a depth-first walk from
        the first box, then from each box not yet walked)."""
        state: dict[str, str] = {}
        back: set[int] = set()
        leaving: dict[str, list[tuple[int, Line]]] = {}
        for i, line in self.on:
            leaving.setdefault(line.from_, []).append((i, line))

        for box in self.flow.boxes:
            if box.id in state:
                continue
            state[box.id] = "open"
            path = [(box.id, iter(leaving.get(box.id, [])))]  # a walk without recursion: a flow may be long
            while path:
                name, lines = path[-1]
                step = next(lines, None)
                if step is None:
                    state[name] = "done"
                    path.pop()
                elif state.get(step[1].to) == "open":
                    back.add(step[0])
                elif step[1].to not in state:
                    state[step[1].to] = "open"
                    path.append((step[1].to, iter(leaving.get(step[1].to, []))))
        return back

    def _leaving(self, name: str) -> "list[tuple[int, Line]]":
        return [(i, line) for i, line in self.ahead if line.from_ == name]

    def _arriving(self, name: str) -> "list[tuple[int, Line]]":
        return [(i, line) for i, line in self.ahead if line.to == name]

    def _fan(self, name: str) -> str | None:
        """The box a DECOMPOSE's tasks join at, when its lines fan out to TASK boxes that each lead on to that one box,
        and nothing else leads into the tasks or the join; else None."""
        if self.boxes[name].type != "decompose":
            return None
        tasks = [line.to for _, line in self._leaving(name)]
        if len(tasks) < 2 or len(set(tasks)) != len(tasks) or any(self.boxes[t].type != "task" for t in tasks):
            return None
        joins = set()
        for task in tasks:
            into, out = self._arriving(task), self._leaving(task)
            if [line.from_ for _, line in into] != [name] or len(out) != 1:
                return None
            joins.add(out[0][1].to)
        if len(joins) != 1:
            return None
        join = joins.pop()
        into_join = [line.from_ for _, line in self._arriving(join)]
        return join if sorted(into_join) == sorted(tasks) else None

    def _fans_and_joins(self) -> None:
        fans = {name: join for name in self.boxes if (join := self._fan(name)) is not None}
        for name in self.boxes:
            out = self._leaving(name)
            if len(out) > 1 and name not in fans:
                for i, _ in out[1:]:
                    self.found.append(
                        (
                            ("lines", i, "from"),
                            f"{name} already goes on to {out[0][1].to}: a box goes on to one box (only a "
                            "DECOMPOSE's tasks fan out, each to the same box after them)",
                        )
                    )
            into = self._arriving(name)
            if len(into) > 1 and name not in fans.values():
                for i, _ in into[1:]:
                    self.found.append(
                        (
                            ("lines", i, "to"),
                            f"{name} is already reached from {into[0][1].from_}: a box is reached by one line (only "
                            "the box after a DECOMPOSE's tasks joins them)",
                        )
                    )
        for name in self.boxes:
            fails = [i for i, line in self.fails if line.from_ == name]
            for i in fails[1:]:
                self.found.append((("lines", i, "from"), f"{name} already has its fail line: a VERIFY has one"))

    def _fail_lines(self) -> None:
        for i, line in self.fails:
            checked = self.boxes[line.from_].checks
            if checked and line.to != checked:
                self.found.append(
                    (
                        ("lines", i, "to"),
                        f"a VERIFY's fail line leads back to the box it checks ({checked}), not {line.to}",
                    )
                )

    def _verify_lines(self) -> None:
        """A VERIFY has two lines: pass to the box after it, and fail back to the box it checks."""
        both = "a VERIFY has two lines, pass to the box after it and fail back to the box it checks"
        for i, box in enumerate(self.flow.boxes):
            if box.type != "verify" or self.boxes[box.id] is not box:
                continue
            if not any(line.from_ == box.id for _, line in self.fails):
                back = f" back to {box.checks}" if box.checks else ""
                self.found.append((("boxes", i, "id"), f"{box.id} has no fail line{back}: {both}"))
            if not any(line.from_ == box.id for _, line in self.on):
                self.found.append(
                    (("boxes", i, "id"), f"{box.id} has no pass line: {both} (a flow ends with a gate, not a VERIFY)")
                )

    def _checks(self) -> None:
        for i, box in enumerate(self.flow.boxes):
            if box.type != "verify" or not box.checks:
                continue
            if box.checks not in self.boxes:
                self.found.append((("boxes", i, "checks"), f"names no box of the flow: {box.checks}"))
            elif box.checks == box.id or box.id not in self._after(box.checks):
                self.found.append(
                    (
                        ("boxes", i, "checks"),
                        f"checks {box.checks}, which does not come before it: a VERIFY checks a box its lines come "
                        "from",
                    )
                )

    def _after(self, name: str) -> set[str]:
        """Every box the lines leading on reach from `name`."""
        found: set[str] = set()
        waiting = [name]
        while waiting:
            for _, line in self._leaving(waiting.pop()):
                if line.to not in found:
                    found.add(line.to)
                    waiting.append(line.to)
        return found

    def _reached(self) -> set[str]:
        first = self.flow.boxes[0].id
        return {first} | self._after(first)


def _tag(box: "Box") -> str:
    return f"{'an' if box.type == 'integrate' else 'a'} {box.type.upper()}"


def _order(place: Place) -> tuple[Any, ...]:
    return tuple((0, part) if isinstance(part, int) else (1, part) for part in place)
