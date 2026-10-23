"""What the Monitor's Flow view shows of a flow (design 0013 §12; boards D1-D4), made in the service, as a session's
flow is (decision 0049): the console draws it, and the phone can later, knowing none of the runner's rules.

`view` is a pure function of the flow, its latest run, the run's batches of proposals, what the main slot runs, the
presets' titles, the brief's text, which files are in the folder and when each box last ended (from the run's events,
since a gate and a YOU box keep no try). It gives:

- **the run**: its number, status, where it is, what it waits for, when it started and ended;
- **every box** in the order the boxes run, with proposals still waiting joined where they would join
  (`proposals.joined`) and marked *proposed*: its state, its preset and mode, its tries (when, how each ended, its
  verdict, the files it wrote, its session), its files, who proposed it and whether the owner edited it, whether it
  asks the owner now, when it last ended, the boxes it leads on to, a gate's files with the box that wrote each, and
  its settings as its file holds them;
- **the lines** of that flow, each *ran*, *now* (into the box running or asking), *not yet*, or for a VERIFY's fail line
  *failed* once a fail took it, with the findings it carried and the tries the checked box used of its cap;
- **the proposals** of the run (the batch with proposals waiting, else the newest: each with its settings, the call
  that proposed it and its state), and the flow's own settings (auto-accept and its cap, waiting after every box, the
  next flow);
- **the next flow** after the last gate (design 0013 §3), once made, else where its brief will come from;
- **how it was built**, for a flow built with the model (design 0013 §15): when, its brief, its planning's state, its
  last draft's warnings and the question that told the owner;
- **Models in this flow** (each preset with its boxes and whether the main slot runs it), **Waiting for you** (the
  question the run waits for, and the next box that will ask), **The brief, checked** (the brief's listed lines, then
  every box's *accept when*, each with the newest verdict's criterion on it: met, not met, or not checked yet),
  **Deliverables** (each file written, with its box, its try and whether its check passed) and **Ahead** (each box
  still to run with what it costs: a switch of the main slot, a fresh prompt, or that it asks the owner);
- **counts** of the boxes by state, and a **version**, the fingerprint of all of it, so a client draws nothing when it
  did not change.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from clank.components.flows.deliverables import written
from clank.components.flows.kinds import Box, Flow
from clank.components.flows.models import OWNERS, named
from clank.components.flows.proposals import Batch, joined
from clank.components.flows.rules import effective_mode
from clank.components.flows.runs import Run, Try, order
from clank.kernel.clock import to_text

LISTED = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+?)\s*$")  # a line of a list in the brief
BRIEF_LINES = 24  # the brief's listed lines read, at most
HAS_RUN = ("done", "failed", "stale", "skipped", "running")


def view(
    id: str,
    made: Flow,
    run: Run | None,
    batches: Sequence[Batch],
    *,
    running: str,
    titles: Mapping[str, str],
    brief: str,
    present: Callable[[str], bool],
    ended: Mapping[str, tuple[datetime, str]],
    next_flow: Mapping[str, Any] | None = None,
    took: Mapping[str, float | None] | None = None,
    built: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """What the Flow view shows of the flow `id`: `made` its flow, `run` its latest run (None: not run yet), `batches`
    that run's proposals, `running` the preset the main slot runs ("" for none), `titles` each preset's title by its
    id, `brief` the brief's text, `present` whether a file is in the folder now, `ended` when each box last ended and
    by whom, `next_flow` the flow made after this one (its `id` and `title`), if any, `took` how long each preset last
    took to come into the main slot here, in seconds (`Flows.switches`), `built` how it was built with the model, when
    it was (design 0013 §15)."""
    workspace, name = id.split("/", 1)
    waiting = [batch for batch in batches if batch.waiting()]
    shown = _with_proposals(made, waiting)
    proposed = {each.id for batch in waiting for each in batch.waiting()}
    edited = {each.id for batch in batches for each in batch.proposals if each.state == "accepted" and each.original}
    by_id = {box.id: box for box in shown.boxes}
    resolve = _resolver(titles)
    states = {name: _state(run, name, proposed) for name in by_id}
    asks = (
        run.waiting.box if run is not None and run.waiting is not None and run.status in ("queued", "running") else ""
    )
    boxes = [_box(shown, by_id[name], run, states[name], resolve, titles, edited, asks, ended) for name in order(shown)]
    found = {
        "flow": id,
        "workspace": workspace,
        "name": name,
        "title": made.title or name,
        "run": _run(run),
        "boxes": boxes,
        "lines": _lines(shown, run, states, asks),
        "proposals": _proposals((waiting or list(batches))[-1], resolve, titles, shown) if batches else None,
        "settings": {
            "auto_accept": made.auto_accept,
            "auto_accept_cap": made.auto_accept_cap,
            "wait_after_every_box": made.wait_after_every_box,
            "next_flow": made.next_flow,
        },
        "next_flow": _next_flow(shown, next_flow),
        "built": dict(built) if built is not None else None,
        **_models(shown, resolve, titles, running),
        **_waiting(shown, run, states, asks),
        "brief": _brief(shown, run, brief),
        "deliverables": _deliverables(shown, run, present),
        "ahead": _ahead(shown, states, resolve, titles, running, took or {}, present),
        "counts": _counts(states),
        "orchestrator": _orchestrator(made, run),
    }
    found["version"] = hashlib.sha256(json.dumps(found, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return found


def _orchestrator(made: Flow, run: Run | None) -> dict[str, Any]:
    """The flow's orchestrator as the Flow view's panel shows it (design 0013 §16): on or off, its limits, and in the
    latest run the checkpoint at work, the last decision with why, what was done and its word for the owner, the limits
    used, and why the run waits for the owner when it could not act or left it to them."""
    settings = made.orchestrator
    state = run.orchestration if run is not None else None
    last = state.decisions[-1] if state is not None and state.decisions else None
    working = state.working if state is not None else None
    return {
        "on": settings.on,
        "role": settings.role,
        "model": settings.model,
        "final_review": settings.final_review,
        "changes": settings.changes,
        "stall_limit": settings.stall,
        "extra_tries": settings.extra_tries,
        "checkpoints": state.checkpoints if state is not None else 0,
        "changes_used": state.changes if state is not None else 0,
        "stall": state.stall if state is not None else 0,
        "working": {"number": working.number, "kind": working.kind, "box": working.box} if working else None,
        "last": {
            "number": last.number,
            "kind": last.kind,
            "box": last.box,
            "choice": last.choice,
            "why": last.why,
            "applied": last.applied,
            "at": to_text(last.at),
            "progressing": last.progressing,
            "looping": last.looping,
            "note": last.note,
            "tell_user": last.tell_user,
            "unmet": list(last.unmet),
        }
        if last is not None
        else None,
        "plan": state.plan if state is not None else "",
        "owner": state.owner if state is not None else "",
    }


def _with_proposals(made: Flow, waiting: Sequence[Batch]) -> Flow:
    """The flow with the proposals still waiting joined where they would join; the flow alone when they would not
    keep its rules (the runner refuses them then, and they show in their batch only)."""
    shown = made
    for batch in waiting:
        try:
            shown = Flow.model_validate(joined(shown, batch, [each.id for each in batch.waiting()]))
        except ValidationError:
            continue
    return shown


def _resolver(titles: Mapping[str, str]) -> Callable[[str], str]:
    by_name = {str(key).lower(): str(key) for key in titles} | {str(t).lower(): str(k) for k, t in titles.items()}

    def resolve(name: str) -> str:
        return by_name.get(name.strip().lower(), name) if name else ""

    return resolve


def _state(run: Run | None, name: str, proposed: set[str]) -> str:
    if name in proposed:
        return "proposed"
    if run is None or name not in run.boxes:
        return "waiting"
    return run.boxes[name].state


def _run(run: Run | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "number": run.number,
        "status": run.status,
        "paused": run.paused,
        "at": run.at,
        "behind": run.behind,
        "created": to_text(run.created),
        "ended": to_text(run.ended) if run.ended else None,
        "waiting": run.waiting.model_dump(mode="json") if run.waiting is not None else None,
    }


def _box(
    flow: Flow,
    box: Box,
    run: Run | None,
    state: str,
    resolve: Callable[[str], str],
    titles: Mapping[str, str],
    edited: set[str],
    asks: str,
    ended: Mapping[str, tuple[datetime, str]],
) -> dict[str, Any]:
    owner = box.type in OWNERS
    preset = "" if owner else resolve(named(flow, box))
    held = run.boxes.get(box.id) if run is not None else None
    tries = [_try(each, run) for each in (held.tries if held is not None and state != "proposed" else [])]
    last_end, by = (tries[-1]["ended"], "") if tries and tries[-1]["ended"] else (None, "")
    if box.id in ended and state != "proposed" and (last_end is None or to_text(ended[box.id][0]) >= last_end):
        last_end, by = to_text(ended[box.id][0]), ended[box.id][1]
    return {
        "id": box.id,
        "type": box.type,
        "title": box.title,
        "state": state,
        "why": held.why if held is not None else "",
        "changed": held.changed if held is not None else "",
        "again": held.again if held is not None else "",
        "preset": preset,
        "preset_title": titles.get(preset, preset),
        "mode": "" if owner else (effective_mode(box) or ""),
        "cap": None if owner else (box.tries or flow.defaults.tries),
        "limits": None
        if owner
        else {
            "minutes": box.limits.minutes or flow.defaults.limits.minutes,
            "tokens": box.limits.tokens or flow.defaults.limits.tokens,
        },
        "tries": tries,
        "writes": list(box.writes),
        "sees": list(box.sees),
        "shows": list(box.shows),
        "checks": box.checks,
        "proposed": box.proposed.model_dump(mode="json") if box.proposed is not None else None,
        "edited": box.id in edited,
        "asks": box.id == asks,
        "ended": last_end,
        "ended_by": by,
        "next": [line.to for line in flow.lines if line.from_ == box.id and line.when != "fail"],
        "shown": [{"path": path, "box": _writer(flow, box, path)} for path in _shows(flow, box)],
        "settings": box.model_dump(mode="json", exclude_none=True),
    }


def _shows(flow: Flow, box: Box) -> list[str]:
    """The files a gate shows: its own `shows`, else the deliverable of the box before it that writes one (as the
    runner's gate question says them); none for another box."""
    from clank.components.flows.runner import _before_writes  # here: the runner builds on what this module's uses

    if box.type != "gate":
        return []
    return list(box.shows) or _before_writes(flow, box)


def _writer(flow: Flow, gate: Box, path: str) -> str:
    """The box that wrote a file a gate shows: the latest before the gate that writes it; empty for none."""
    before: list[Box] = []
    for name in order(flow):
        if name == gate.id:
            break
        before += [each for each in flow.boxes if each.id == name]
    return next((each.id for each in reversed(before) if path in each.writes), "")


def _try(made: Try, run: Run | None) -> dict[str, Any]:
    before = {kept.path: kept for kept in made.before}
    files = [kept.path for kept in made.deliverables if written(before.get(kept.path), kept)]
    verdict = made.verdict
    return {
        "number": made.number,
        "started": to_text(made.started),
        "ended": to_text(made.ended) if made.ended else None,
        "outcome": made.outcome,
        "reason": made.reason,
        "tokens": made.tokens,
        "agent": made.agent,
        "mode": made.mode,
        "told": made.told,
        "session": {"workspace": run.workspace, "port": made.port, "session": made.session}
        if made.session and run is not None
        else None,
        "written": files,
        "verdict": {
            "result": verdict.result,
            "findings": list(verdict.findings),
            "criteria": [each.model_dump(mode="json") for each in verdict.criteria],
            "checked": verdict.checked,
            "given": to_text(verdict.given),
        }
        if verdict is not None
        else None,
        "command": made.command.model_dump(mode="json") if made.command is not None else None,
    }


def _lines(flow: Flow, run: Run | None, states: Mapping[str, str], asks: str) -> list[dict[str, Any]]:
    found = []
    for line in flow.lines:
        source, target = states.get(line.from_, "waiting"), states.get(line.to, "waiting")
        said: dict[str, Any] = {"from": line.from_, "to": line.to, "when": line.when}
        if line.when == "fail":
            said |= _fail(flow, run, line.from_)
        elif target == "running" or line.to == asks:
            said["state"] = "now" if source not in ("waiting", "proposed") else "not yet"
        elif target in HAS_RUN and source in HAS_RUN:
            said["state"] = "ran"
        else:
            said["state"] = "not yet"
        found.append(said)
    return found


def _fail(flow: Flow, run: Run | None, verify: str) -> dict[str, Any]:
    """A VERIFY's fail line: taken once a fail sent the checked box back, with the newest fail's findings, and the tries
    the checked box used of its cap."""
    box = next(each for each in flow.boxes if each.id == verify)
    checked = next((each for each in flow.boxes if each.id == box.checks), None)
    cap = (checked.tries if checked is not None else None) or flow.defaults.tries
    tries = run.boxes[verify].tries if run is not None and verify in run.boxes else []
    fails = [each.verdict for each in tries if each.verdict is not None and each.verdict.result == "fail"]
    used = len(run.boxes[box.checks].tries) if run is not None and box.checks in run.boxes else 0
    if not fails:
        return {"state": "not yet", "findings": 0, "used": used, "cap": cap}
    return {"state": "failed", "findings": len(fails[-1].findings), "used": used, "cap": cap}


def _proposals(batch: Batch, resolve: Callable[[str], str], titles: Mapping[str, str], flow: Flow) -> dict[str, Any]:
    items = []
    for each in batch.proposals:
        box = each.box
        preset = "" if box.type in OWNERS else resolve(named(flow, box))
        items.append(
            {
                "id": each.id,
                "number": each.number,
                "after": each.after,
                "state": each.state,
                "type": box.type,
                "title": box.title,
                "prompt": box.prompt,
                "writes": list(box.writes),
                "holds": box.holds,
                "sees": list(box.sees),
                "accept_when": list(box.accept_when),
                "preset": preset,
                "preset_title": titles.get(preset, preset),
                "mode": box.mode or "",
                "why": each.why,
                "given": to_text(each.given),
                "edited": each.original is not None,
                "said": each.said,
            }
        )
    return {
        "box": batch.box,
        "try": batch.attempt,
        "summary": batch.summary,
        "submitted": to_text(batch.submitted) if batch.submitted else None,
        "question": batch.question,
        "waiting": [each.id for each in batch.waiting()],
        "items": items,
    }


def _next_flow(flow: Flow, made: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The next flow, after the last gate (design 0013 §3): once made, its id and title; before, where its brief will
    come from (the last INTEGRATE), when the flow ends with a gate after one."""
    if made:
        return {"id": str(made.get("id") or ""), "title": str(made.get("title") or ""), "from": ""}
    ordered = order(flow)
    types = {box.id: box.type for box in flow.boxes}
    integrates = [name for name in ordered if types.get(name) == "integrate"]
    if not ordered or types.get(ordered[-1]) != "gate" or not integrates or flow.next_flow == "off":
        return None
    return {"id": "", "title": "", "from": integrates[-1]}


def _models(flow: Flow, resolve: Callable[[str], str], titles: Mapping[str, str], running: str) -> dict[str, Any]:
    used: dict[str, int] = {}
    yours = 0
    for box in flow.boxes:
        if box.type in OWNERS:
            yours += 1
            continue
        preset = resolve(named(flow, box)) or running
        used[preset] = used.get(preset, 0) + 1
    models = [
        {"preset": preset, "title": titles.get(preset, preset), "loaded": bool(preset) and preset == running,
         "boxes": count}
        for preset, count in used.items()
    ]  # fmt: skip
    return {"models": models, "yours": yours}


def _waiting(flow: Flow, run: Run | None, states: Mapping[str, str], asks: str) -> dict[str, Any]:
    """What the flow waits for now (the run's question), and the next box that will ask the owner, with the box before
    it."""
    titles = {box.id: box.title for box in flow.boxes}
    waiting = []
    if run is not None and run.waiting is not None and asks:
        said = run.waiting
        waiting.append({"kind": said.kind, "box": said.box, "title": titles.get(said.box, said.box),
                        "question": said.question})  # fmt: skip
    ordered = order(flow)
    types = {box.id: box.type for box in flow.boxes}
    next_ask = None
    for index, name in enumerate(ordered):
        if types.get(name) in OWNERS and states.get(name) in ("waiting", "stale") and name != asks:
            next_ask = {"box": name, "title": titles[name], "after": ordered[index - 1] if index else ""}
            break
    return {"waiting": waiting, "next_ask": next_ask}


def _normal(line: str) -> str:
    return " ".join(line.lower().split()).rstrip(".")


def _brief(flow: Flow, run: Run | None, text: str) -> dict[str, Any]:
    """The brief's listed lines, then every box's *accept when*, each with the newest criterion a verdict gave on it."""
    first = flow.boxes[0]
    file = first.writes[0] if first.type == "you" and first.writes else ""
    lines: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(line: str, source: str) -> None:
        key = _normal(line)
        if key and key not in seen:
            seen.add(key)
            lines.append({"line": line, "source": source, "met": None, "evidence": "", "by": "", "try": None})

    for listed in (LISTED.match(row) for row in text.splitlines()):
        if listed is not None and len(lines) < BRIEF_LINES:
            add(listed.group(1), "brief")
    for name in order(flow):
        box = next(each for each in flow.boxes if each.id == name)
        for accept in box.accept_when:
            add(accept, box.id)
    newest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for name, held in run.boxes.items() if run is not None else []:
        for each in held.tries:
            verdict = each.verdict
            if verdict is None:
                continue
            for criterion in verdict.criteria:
                key = _normal(criterion.line)
                if key not in newest or verdict.given >= newest[key][0]:
                    said = {"line": criterion.line, "met": criterion.met, "evidence": criterion.evidence}
                    newest[key] = (verdict.given, {**said, "by": name, "try": each.number})
    for key, (_, given) in newest.items():
        if key not in seen:
            add(str(given["line"]), "verdict")
    for row in lines:
        on = newest.get(_normal(row["line"]))
        if on is not None:
            row.update({key: on[1][key] for key in ("met", "evidence", "by", "try")})
    return {"file": file, "lines": lines, "met": sum(1 for row in lines if row["met"]), "of": len(lines)}


def _deliverables(flow: Flow, run: Run | None, present: Callable[[str], bool]) -> list[dict[str, Any]]:
    """Every file the run's boxes wrote, in the order they run: its box, the try that wrote it last, whether its check
    passed (the newest verdict of a VERIFY that checks the box, else its accept command), and whether it is in the
    folder now."""
    if run is None:
        return []
    found: list[dict[str, Any]] = []
    verifies = [box for box in flow.boxes if box.type == "verify"]
    for name in order(flow):
        box = next(each for each in flow.boxes if each.id == name)
        held = run.boxes.get(name)
        if held is None:
            continue
        if box.type in OWNERS:
            found += [{"path": kept.path, "box": name, "try": None, "passed": None, "present": present(kept.path)}
                      for kept in held.kept if kept.sha256]  # fmt: skip
            continue
        last: dict[str, Try] = {}
        for each in held.tries:
            before = {kept.path: kept for kept in each.before}
            for kept in each.deliverables:
                if written(before.get(kept.path), kept):  # as the runner counts it: its fingerprint, size or time
                    last[kept.path] = each
        for path in [path for path in box.writes if path in last] + [p for p in last if p not in box.writes]:
            made = last[path]
            found.append({"path": path, "box": name, "try": made.number, "passed": _passed(run, verifies, name, made),
                          "present": present(path)})  # fmt: skip
    return found


def _passed(run: Run, verifies: Sequence[Box], name: str, made: Try) -> bool | None:
    newest = None
    for verify in verifies:
        if verify.checks != name or verify.id not in run.boxes:
            continue
        for each in run.boxes[verify.id].tries:
            verdict = each.verdict
            fits = verdict is not None and verdict.checked in (None, made.number)
            if fits and verdict is not None and (newest is None or verdict.given >= newest.given):
                newest = verdict
    if newest is not None:
        return newest.result == "pass"
    return made.command.passed if made.command is not None else None


def _ahead(
    flow: Flow,
    states: Mapping[str, str],
    resolve: Callable[[str], str],
    titles: Mapping[str, str],
    running: str,
    took: Mapping[str, float | None],
    present: Callable[[str], bool] = lambda path: False,
) -> list[dict[str, Any]]:
    """Each box still to run, in order, with what it costs: a switch of the main slot to its preset (and how long that
    preset last took to come in here, when known), a fresh prompt, or that it asks the owner; a built flow's first YOU
    is done by the brief written with the model when its files are in the folder (design 0013 §15)."""
    found = []
    current = running
    for name in order(flow):
        if states.get(name) not in ("waiting", "proposed", "stale"):
            continue
        box = next(each for each in flow.boxes if each.id == name)
        briefed = flow.built is not None and box is flow.boxes[0] and box.writes
        if briefed and all(present(path) for path in box.writes):
            found.append({"box": name, "costs": [f"done by {', '.join(box.writes)}, written with the model"]})
            continue
        if box.type in OWNERS:
            found.append({"box": name, "costs": ["asks you"]})
            continue
        costs = []
        preset = resolve(named(flow, box)) or current
        if preset and preset != current:
            seconds = took.get(preset)
            said = f", which last took {seconds:.0f} s here" if seconds is not None else ""
            costs.append(f"a switch to {titles.get(preset, preset)}{said}")
            current = preset
        costs.append("a fresh prompt")
        found.append({"box": name, "costs": costs})
    return found


def _counts(states: Mapping[str, str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for state in states.values():
        found[state] = found.get(state, 0) + 1
    return dict(sorted(found.items(), key=lambda pair: ORDER.index(pair[0]) if pair[0] in ORDER else len(ORDER)))


ORDER = ("done", "running", "waiting", "proposed", "failed", "stale", "skipped")
