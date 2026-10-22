"""The words of the Flow view's panels beside and under the flow (design 0013 §12, board D1), each a function of what
the service says of the flow (`GET /flows/view`) and the panel's width, returning lines cut with the style's "…" so
nothing spills (decision 0045); the whole of each is one key away (`?`, Enter).

- **Selected** (`selected`): the box chosen, its tag and state, its title, then a row for each of its settings and
  states (its model, its status since when, its mode, what it sees, where its prompt came from, what it writes, what
  comes after it, a VERIFY's pass and fail lines), then its tries and a VERIFY's newest findings.
- **Live** (`live`), inside Selected while a model's box runs: its phase and step, its speed and each step's, its
  context window as a bar, the loop guard, and that Enter opens its session (design 0012's Session view).
- **Models in this flow** (`models`): each preset with how many boxes use it and whether the main slot runs it.
- **Waiting for you** (`waiting`): what the flow waits for now, else that nothing does and the next box that will ask;
  for a flow built with the model and not run yet (design 0013 §15), that it was built, to look, then `r`, and the
  check's warnings of its last draft, each whole, wrapped (`wrapped`), never cut.
- **The brief, checked** (`brief`): each line of the brief and of every *accept when*, met, not met or not checked
  yet, with its evidence and the check that said so.
- **Deliverables** (`deliverables`): each file written, its box and try, and whether its check passed.
- **Ahead** (`ahead`): each box still to run with what it costs.

`LinesView` holds a panel's lines: it draws them again only when they changed, for its width (on a resize too), and
counts its draws for the tests.
"""

import textwrap
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, tzinfo
from typing import Any

from textual import events
from textual.content import Content
from textual.widgets import ListView, Static

from clank.components.agents.console.boxchart import TAGS, TONES, model_said, state_mark, tag
from clank.components.agents.console.flowchart import cut
from clank.components.agents.console.nowpanel import head
from clank.console.gauges import spark
from clank.console.lists import refill
from clank.console.style import current, mark
from clank.console.text import clock, duration, parse

LABEL = 8  # the column the rows' values start at: "prompt" and two spaces
WIDE = 400  # the width the Deliverables list's rows are made for: the list cuts them to the panel
WIDTH = 40  # the width drawn for before the panel is laid out
NO_FLOW = "no flow yet"
STATES = {"done": "done", "running": "running", "waiting": "waiting", "failed": "failed", "stale": "stale",
          "skipped": "skipped", "proposed": "proposed: not in the flow until you accept it"}  # fmt: skip
WAITS_FOR = {
    "gate": "your decision",
    "you": "your part",
    "failed": "a box that failed: your call",
    "done": "your go-ahead",
    "proposals": "your decision on its proposals",
}
MODES = {"plan": "plan: Markdown only", "review": "review: changes wait for you",
         "auto": "auto: changes accepted at once"}  # fmt: skip

Line = Content


def _fit(line: Content, width: int) -> Content:
    """A line cut to `width` cells, ending in the style's mark of cut text when it was cut."""
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)


def _row(label: str, value: Content | str, width: int) -> Content:
    said = value if isinstance(value, Content) else Content(value)
    return _fit(Content.assemble((f"{label:<{LABEL}}", "$clank-quiet"), said), width)


def _box(view: Mapping[str, Any], id: str) -> Mapping[str, Any] | None:
    return next((box for box in view.get("boxes") or [] if box["id"] == id), None)


def _tagged(box: Mapping[str, Any]) -> Content:
    return Content.assemble((tag(box), f"bold {TONES.get(str(box['type']), '$clank-text')}"), " ", box["title"])


def _when(text: str | None, zone: tzinfo | None) -> str:
    return clock(parse(text), zone) if text else ""


def selected(
    view: Mapping[str, Any] | None, id: str, width: int, zone: tzinfo | None, now: datetime | None = None
) -> list[Content]:
    """Selected: the box chosen, its settings and states, its tries and a VERIFY's newest findings."""
    if not view or not view.get("flow"):
        return [Content.styled(NO_FLOW, "$clank-quiet")]
    if id == "next-flow":
        following = view.get("next_flow") or {}
        said = following.get("title") or "made from INTEGRATE's brief once you approve the last gate"
        return [_fit(Content.styled("next flow", "bold $clank-quiet"), width), _fit(Content(said), width)]
    box = _box(view, id)
    if box is None:
        return [Content.styled("no box chosen: the arrows choose one", "$clank-quiet")]
    right, tone = state_mark(box, {})
    words = STATES.get(str(box["state"]), str(box["state"]))
    lines = [
        _fit(
            Content.assemble(
                (tag(box), f"bold {TONES.get(str(box['type']), '$clank-text')}"),
                " · ",
                (f"{right.split(' ')[0]} {words}", tone),
            ),
            width,
        ),
        _fit(Content.styled(box["title"], "bold"), width),
    ]
    lines += [_row(label, value, width) for label, value in _rows(view, box, zone, now)]
    lines += _tries(view, box, width, zone)
    return lines


def _rows(
    view: Mapping[str, Any], box: Mapping[str, Any], zone: tzinfo | None, now: datetime | None
) -> list[tuple[str, Content | str]]:
    kind, state = box["type"], box["state"]
    boxes = {each["id"]: each for each in view.get("boxes") or []}
    rows: list[tuple[str, Content | str]] = [("model", model_said(box, {}))]
    cost = (((view.get("cost") or {}).get("boxes") or {}).get(str(box["id"])) or {}).get("said")
    if cost:
        rows.append(("cost", cost))
    rows.append(("status", _status(box, zone, now)))
    if box.get("mode"):
        rows.append(("mode", MODES.get(str(box["mode"]), str(box["mode"]))))
    if box.get("sees"):
        rows.append(("sees", ", ".join(box["sees"])))
    if kind == "verify" and box.get("checks") in boxes:
        rows.append(("checks", _tagged(boxes[box["checks"]])))
    if kind == "gate" and box.get("shows"):
        rows.append(("shows", ", ".join(box["shows"])))
    proposed = box.get("proposed") or {}
    if proposed:
        rows.append(("prompt", f"{proposed.get('by')}'s draft" + (", edited by you" if box.get("edited") else "")))
    if box.get("writes"):
        written = {path for each in box["tries"] for path in each.get("written") or []}
        files = ", ".join(box["writes"])
        rows.append(("writes", files if state != "running" or written else f"{files} (not yet)"))
    if box.get("why") and state in ("failed", "stale"):
        rows.append(("why", Content.styled(str(box["why"]), "$clank-attention")))
    following = after(boxes, box)
    if kind == "verify":
        if following:
            rows.append(("pass", Content.assemble((f"{_arrow()} ", "$clank-good"), _tagged(following[0]))))
        if box.get("checks") in boxes:
            back = TAGS.get(str(boxes[box["checks"]]["type"]), box["checks"])
            rows.append(("fail", Content.assemble(("⟲ ", "$clank-failed"), f"back to {back} with the findings")))
    elif len(following) == 1:
        rows.append(("next", _tagged(following[0])))
    elif following:
        rows.append(("next", ", ".join(each["id"] for each in following) + " (one after another)"))
    return rows


def after(boxes: Mapping[str, Mapping[str, Any]], box: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The boxes that come after a box: where its lines lead, but for a DECOMPOSE's task, the next task of its fan (they
    run one after another), the last one's the box they join at."""
    following = [boxes[name] for name in box.get("next") or [] if name in boxes]
    fan = [each for each in boxes.values() if each["type"] == "task" and each.get("next") == box.get("next")]
    if box["type"] == "task" and len(fan) > 1 and fan[-1]["id"] != box["id"]:
        return [fan[[each["id"] for each in fan].index(box["id"]) + 1]]
    return following


def _arrow() -> str:
    return current().tree.arrow


def _status(box: Mapping[str, Any], zone: tzinfo | None, now: datetime | None) -> Content:
    state = box["state"]
    right, tone = state_mark(box, {})
    sign = right.split(" ")[0]
    tries = box.get("tries") or []
    if state == "running" and box.get("asks"):
        return Content.assemble((f"{sign} ", tone), "waits for you")
    if state == "running" and tries:
        started = parse(tries[-1]["started"])
        since = f"running since {clock(started, zone)}"
        if now is not None:
            since += f" · {duration(max((now - started).total_seconds(), 0))}"
        return Content.assemble((f"{sign} ", tone), since, (f" · try {tries[-1]['number']} of {box.get('cap')}",
                                                             "$clank-quiet"))  # fmt: skip
    ended = _when(box.get("ended"), zone)
    if state == "done":
        by = f" by {box['ended_by']}" if box.get("ended_by", "").startswith("you") else ""
        many = f" · {len(tries)} tries" if len(tries) > 1 else ""
        return Content.assemble((f"{sign} ", tone), f"done {ended}".strip() + by, (many, "$clank-quiet"))
    if state == "waiting":
        return Content.assemble((f"{sign} ", tone), ("waiting", "$clank-quiet"))
    return Content.assemble((f"{sign} ", tone), STATES.get(str(state), str(state)))


def _tries(view: Mapping[str, Any], box: Mapping[str, Any], width: int, zone: tzinfo | None) -> list[Content]:
    """Its tries, each with when and how it ended; a VERIFY's newest fail's findings, numbered."""
    tries = box.get("tries") or []
    lines: list[Content] = []
    if len(tries) > 1 or (tries and tries[-1].get("verdict")):
        lines.append(Content.styled("Tries", "bold $clank-title"))
        for each in tries:
            span = f"{_when(each['started'], zone)} to {_when(each.get('ended'), zone)}".removesuffix(" to ")
            verdict = each.get("verdict")
            if verdict:
                passed = verdict["result"] == "pass"
                sign, tone = (mark("done"), "$clank-good") if passed else (mark("failed"), "$clank-failed")
                count = len(verdict.get("findings") or [])
                found = f", {count} finding{'s' if count != 1 else ''}" if verdict["result"] == "fail" else ""
                said = Content.assemble((f"{sign} ", tone), f"{verdict['result']}{found}")
            elif each.get("outcome"):
                said = Content(f"{each['outcome']}" + (f": {each['reason']}" if each.get("reason") else ""))
            else:
                said = Content.styled("running", "$clank-now")
            wrote = " · wrote " + ", ".join(each["written"]) if each.get("written") else ""
            lines.append(_fit(Content.assemble((f"try {each['number']}  ", "$clank-quiet"), f"{span} ", said,
                                               (wrote, "$clank-quiet")), width))  # fmt: skip
    fails = [each["verdict"] for each in tries if (each.get("verdict") or {}).get("result") == "fail"]
    if fails:
        lines.append(Content.styled(f"Its newest findings ({len(fails[-1]['findings'])})", "bold $clank-failed"))
        for number, finding in enumerate(fails[-1]["findings"], start=1):
            lines.append(_fit(Content.assemble((f"{number}  ", "$clank-failed"), str(finding)), width))
    return lines


def live(
    box: Mapping[str, Any] | None, now: Mapping[str, Any] | None, context: Mapping[str, Any] | None, width: int
) -> list[Content]:
    """Live, inside Selected while a model's box runs: its phase and step, its speed, its context window, the loop
    guard, and that Enter opens its session."""
    if box is None:
        return []
    lines = [
        _fit(head(dict(now)) if now is not None else Content.styled("reading what it does", "$clank-quiet"), width)
    ]
    speed = (now or {}).get("speed") or {}
    steps = [float(each) for each in speed.get("steps") or []]
    current_speed = speed.get("now")
    said = f"{current_speed:.0f} tok/s" if current_speed else "no speed yet"
    shown = Content.assemble(("speed   ", "$clank-quiet"), said)
    if steps and width - shown.cell_length > 4:
        shown = Content.assemble(shown, " ", spark(steps, min(len(steps), width - shown.cell_length - 1),
                                                   top=max(steps)))  # fmt: skip
    lines.append(_fit(shown, width))
    totals = context or {}
    window, used = totals.get("window"), totals.get("used")
    if window and used is not None:
        share = used / window
        cells = max(min(width - LABEL - 24, 20), 4)
        filled = round(share * cells)
        bar = Content.assemble(("█" * filled, "$clank-low"), ("░" * (cells - filled), "$clank-border"))
        lines.append(_row("context", Content.assemble(bar, f" {share:.0%} · {used:,} of {window:,}"), width))
    else:
        why = "not read yet" if context is None else ("no model runs" if not window else "no step has ended yet")
        lines.append(_row("context", Content.styled(why, "$clank-quiet"), width))
    guard = (now or {}).get("guard") or {}
    if guard.get("stopped"):
        said_guard: Content | str = Content.styled(f"stopped {guard['stopped']}", "$clank-failed")
    else:
        said_guard = "watching · nothing repeats" if guard.get("on") else "off"
    lines.append(_row("guard", said_guard, width))
    lines.append(_fit(Content.styled("Enter opens its session: the Session view and its Guide", "$clank-quiet"), width))
    return lines


def models(view: Mapping[str, Any] | None, width: int) -> list[Content]:
    """Models in this flow: each preset, how many boxes use it, whether the main slot runs it."""
    if not view or not view.get("flow"):
        return [Content.styled(NO_FLOW, "$clank-quiet")]
    lines = []
    for each in view.get("models") or []:
        loaded = each.get("loaded")
        sign = Content.styled(f"{mark('on') if loaded else mark('off')} ", "$clank-good" if loaded else "$clank-quiet")
        boxes = f"{each['boxes']} box{'es' if each['boxes'] != 1 else ''}"
        said = (" · loaded", "$clank-good") if loaded else (" · loads before its first box", "$clank-quiet")
        if not each.get("title"):  # no preset named: its boxes run on what the main slot runs, switching nothing
            said = (" · switches nothing", "$clank-quiet")
        lines.append(_fit(Content.assemble(sign, (each.get("title") or "main slot's model", "bold"), said,
                                           (f" · {boxes}", "$clank-quiet")), width))  # fmt: skip
    cost = (view.get("cost") or {}).get("said")  # the cloud's, in the service's words (design 0016 §11)
    if cost:
        lines.append(_fit(Content(f"this flow so far: {cost}"), width))
    yours = int(view.get("yours") or 0)
    if yours:
        lines.append(_fit(Content.styled(f"the other {yours} {'are' if yours != 1 else 'is'} you", "$clank-quiet"),
                          width))  # fmt: skip
    lines.append(_fit(Content.styled("e on a box picks another preset for it", "$clank-quiet"), width))
    return lines


def waiting(view: Mapping[str, Any] | None, width: int) -> list[Content]:
    """Waiting for you: what the flow waits for now, else that nothing does and the next box that will ask; while the
    flow is built with the model, how to talk with it."""
    if not view or not view.get("flow"):
        return [Content.styled(NO_FLOW, "$clank-quiet")]
    if view.get("planning"):
        return talking(view["planning"], width)
    boxes = {box["id"]: box for box in view.get("boxes") or []}
    lines = []
    for each in view.get("waiting") or []:
        box = boxes.get(each["box"])
        what = WAITS_FOR.get(each["kind"], each["kind"])
        named = _tagged(box) if box else Content(str(each["title"]))
        lines.append(_fit(Content.assemble((f"{mark('asks')} ", "bold $clank-attention"), named), width))
        said = f"  waits for {what}: Enter on it, here or on your phone"
        lines.append(_fit(Content.styled(said, "$clank-quiet"), width))
    proposals = view.get("proposals") or {}
    if proposals.get("waiting") and not any(each["kind"] == "proposals" for each in view.get("waiting") or []):
        count = len(proposals["waiting"])
        said = f"{count} proposal{'s' if count != 1 else ''} of {proposals['box']}"
        lines.append(_fit(Content.assemble((f"{mark('asks')} ", "bold $clank-attention"), said), width))
    built = view.get("built") or {}
    if built and not view.get("run") and not lines:  # built with the model, not run yet (design 0013 §15)
        return built_lines(built, width)
    if not lines:
        lines.append(_fit(Content.assemble((f"{mark('done')} ", "$clank-good"), "Nothing waits for you."), width))
        following = view.get("next_ask")
        if following and following["box"] in boxes:
            after = boxes.get(following.get("after") or "")
            later = (f", after {tag(after)}" if after else "", "$clank-quiet")
            named = _tagged(boxes[following["box"]])
            lines.append(_fit(Content.assemble(("next: ", "$clank-quiet"), named, later), width))
            lines.append(_fit(Content.styled("it asks here and on your phone", "$clank-quiet"), width))
    return lines


def talking(planning: Mapping[str, Any], width: int) -> list[Content]:
    """Waiting for you, while a flow is built with the model (decision 0101): how to talk with the model while its
    session has not started (in Clank's VS Code window for one opened there; to wait while it starts on its window);
    then that it is there, and that Enter opens its session here; for a planning that failed, why, and how to try it
    again."""
    if planning.get("status") == "failed":
        why = planning.get("why") or "no reason given"
        return wrapped(f"the planning failed: {why}; to try it again, in another terminal, {planning.get('attach')}; "
                       "or n opens another", width, (f"{mark('failed')} ", "$clank-failed"), style="")  # fmt: skip
    vscode = planning.get("where") == "vscode"
    if planning.get("status") == "opening":
        window = "OpenCode in Clank's VS Code window" if vscode else "the OpenCode window it was attached to"
        return wrapped(f"its session starts on {window}: wait for it there", width,
                       (f"{mark('on')} ", "$clank-now"), style="")  # fmt: skip
    if not planning.get("session") and vscode:
        return wrapped("OpenCode opens in Clank's VS Code window, on this planning: talk with the model there", width,
                       (f"{mark('asks')} ", "bold $clank-attention"), style="")  # fmt: skip
    if not planning.get("session"):
        return wrapped(f"talk with the model: in another terminal, {planning.get('attach')}", width,
                       (f"{mark('asks')} ", "bold $clank-attention"), style="")  # fmt: skip
    lines = wrapped(f"talk with the model in OpenCode, on “{planning.get('title')}”", width,
                    (f"{mark('asks')} ", "bold $clank-attention"), style="")  # fmt: skip
    lines += wrapped("Enter opens its session here; once the model's draft is written: look, then r", width)
    return lines


def building(view: Mapping[str, Any] | None, width: int, zone: tzinfo | None) -> list[Content]:
    """Building it with the model, in Selected's place (decision 0101): the planning's steps, each draft with its
    problems, whole and wrapped, never cut; for a planning that failed, how to try it again."""
    planning = (view or {}).get("planning") or {}
    marks = {
        "started": (mark("done"), "$clank-good"), "waits": (mark("off"), "$clank-quiet"),
        "opening": (mark("on"), "$clank-now"), "reading": (mark("on"), "$clank-now"),
        "brief": (mark("done"), "$clank-good"), "waiting": (mark("asks"), "bold $clank-attention"),
        "failed": (mark("failed"), "$clank-failed"), "note": (mark("asks"), "$clank-attention"),
    }  # fmt: skip
    lines: list[Content] = []
    for step in planning.get("steps") or []:
        kind = str(step.get("kind"))
        at = _when(step.get("at"), zone)
        if kind == "draft":
            refused = step.get("state") == "refused"
            sign = (mark("failed"), "$clank-failed") if refused else (mark("done"), "$clank-good")
            count = len(step.get("problems") or [])
            said = (
                f"draft {step['number']}"
                + (f" · {at}" if at else "")
                + (f" · refused: {count} problem{'s' if count != 1 else ''}" if refused else " · accepted")
            )
            lines += wrapped(said, width, (f"{sign[0]} ", sign[1]), style="")
            for problem in step.get("problems") or []:
                lines += wrapped(str(problem), width, ("    - ", "$clank-failed"))
            continue
        shown, tone = marks.get(kind, (mark("off"), "$clank-quiet"))
        said = str(step.get("said") or kind) + (f" · {at}" if at else "")
        lines += wrapped(said, width, (f"{shown} ", tone), style="")
        if kind == "failed":  # said here too: on a stacked page, Waiting for you may be below the screen
            again = f"to try it again, in another terminal, {planning.get('attach')}; or n opens another"
            lines += wrapped(again, width, ("  ", ""), style="")
    return lines or [Content.styled("starting", "$clank-quiet")]


def built_lines(built: Mapping[str, Any], width: int) -> list[Content]:
    """Waiting for you, for a flow built with the model and not run yet (design 0013 §15): built, look, then r; and
    the check's warnings of its last draft, each whole, wrapped, never cut."""
    lines = wrapped("Built with the model: look, then r to run", width, (f"{mark('asks')} ", "bold $clank-attention"))
    lines += wrapped(
        "e changes a box first; r runs it from its brief to your review, asking nothing else on the way", width
    )
    warnings = list(built.get("warnings") or [])
    if warnings:
        lines.append(_fit(Content.styled("The check warns:", "$clank-attention"), width))
        for each in warnings:
            lines += wrapped(each, width, ("- ", "$clank-attention"), style="")
    return lines


def wrapped(
    text: str, width: int, first: tuple[str, str] = ("  ", ""), *, style: str = "$clank-quiet"
) -> list[Content]:
    """A text wrapped to `width` cells, never cut: its first line after `first` (a mark, with its style), the others
    indented as far."""
    lead, tone = first
    room = max(width - len(lead), 8)
    parts = textwrap.wrap(text, room, break_long_words=True, break_on_hyphens=False) or [""]
    return [
        Content.assemble((lead if index == 0 else " " * len(lead), tone), (part, style) if style else part)
        for index, part in enumerate(parts)
    ]


def orchestrator(view: Mapping[str, Any] | None, width: int, frame: int = 0) -> list[Content]:
    """The Orchestrator panel (design 0013 §16): off, what turning it on does; on, its model, who decides the final
    review, the limits used, the checkpoint at work, the last decision with why and what was done, the note the next
    box is told, the plan from here, and why the run waits for you when it could not act."""
    if not view or not view.get("flow"):
        return [Content.styled(NO_FLOW, "$clank-quiet")]
    said = view.get("orchestrator") or {}
    if not said.get("on"):
        lines = [_fit(Content.assemble((f"{mark('off')} ", "$clank-quiet"), ("off", "bold")), width)]
        lines += wrapped(
            "O turns it on: a model reads what each box did, changes the boxes ahead or sends work back, and answers "
            "the run's questions (a box out of tries, a gate) as you would, within limits you set; L shows its ledger.",
            width,
        )
        return lines
    final = (
        "decides the final review too" if said.get("final_review") == "orchestrator" else "the final review is yours"
    )
    model = str(said.get("model") or "the flow's model")
    lines = [
        _fit(
            Content.assemble(
                (f"{mark('done')} ", "$clank-good"), ("on", "bold"), (f" · {model} · {final}", "$clank-quiet")
            ),
            width,
        ),
        _fit(
            Content.styled(
                f"checkpoints {said.get('checkpoints', 0)} · changes {said.get('changes_used', 0)} of "
                f"{said.get('changes', 0)} · stall {said.get('stall', 0)} of {said.get('stall_limit', 0)}",
                "$clank-quiet",
            ),
            width,
        ),
    ]
    working = said.get("working")
    if working:
        where = f"after {working['box']}" if working["kind"] == "review" else f"at {working['box']}'s question"
        lines.append(
            _fit(
                Content.assemble(
                    (f"{spark_spin(frame)} ", "$clank-now"),
                    (f"checkpoint {working['number']}: reads the run {where}", "bold"),
                ),
                width,
            )
        )
    last = said.get("last")
    if last:
        where = f"after {last['box']}" if last["kind"] == "review" else f"at {last['box']}"
        tone = "$clank-failed" if last["choice"] == "stop" else "$clank-good"
        lines.append(_fit(Content.assemble(("last: ", "$clank-quiet"), (f"{last['choice']} ", f"bold {tone}"),
                                           (where, "$clank-quiet")), width))  # fmt: skip
        lines += wrapped(str(last.get("why") or ""), width, style="")
        if last.get("applied"):
            lines += wrapped(str(last["applied"]), width)
        if last.get("note"):
            lines += wrapped(f"told the next box: {last['note']}", width)
        if not last.get("progressing", True) or last.get("looping"):
            lines.append(_fit(Content.styled("  no progress at this checkpoint", "$clank-attention"), width))
    if said.get("owner"):
        lines += wrapped(str(said["owner"]), width, (f"{mark('asks')} ", "bold $clank-attention"), style="")
    plan = str(said.get("plan") or "").strip()
    if plan:
        lines += wrapped(f"plan: {plan.splitlines()[0]}", width)
    return lines


def spark_spin(frame: int) -> str:
    """The spinner's glyph at `frame`, as the header draws it."""
    from clank.console.gauges import spinner

    return spinner(frame)


def brief(view: Mapping[str, Any] | None, width: int) -> list[Content]:
    """The brief, checked: each line, met, not met or not checked yet, with its evidence and the check that said so."""
    if not view or not view.get("flow"):
        return [Content.styled(NO_FLOW, "$clank-quiet")]
    said = view.get("brief") or {}
    lines = []
    for each in said.get("lines") or []:
        met = each.get("met")
        if met is None:
            sign, tone, evidence = mark("off"), "$clank-quiet", "not checked yet"
        else:
            sign, tone = (mark("done"), "$clank-good") if met else (mark("failed"), "$clank-failed")
            evidence = str(each.get("evidence") or ("met" if met else "not met"))
            if each.get("by"):
                evidence += f" · {each['by']}, try {each.get('try')}"
        lines.append(_fit(Content.assemble((f"{sign} ", tone), str(each["line"]), (f"  {evidence}", "$clank-quiet")),
                          width))  # fmt: skip
    if not lines:
        where = said.get("file") or "the brief"
        lines.append(_fit(Content.styled(f"{where} lists no line, and no box says what it is accepted when",
                                         "$clank-quiet"), width))  # fmt: skip
    return lines


def brief_note(view: Mapping[str, Any] | None) -> str:
    """The panel's note: how many lines are met."""
    said = (view or {}).get("brief") or {}
    return f"{said.get('met', 0)} of {said.get('of', 0)} met" if said.get("of") else ""


def deliverables(view: Mapping[str, Any] | None, width: int) -> list[Content]:
    """Deliverables: each file written, its box and try, whether its check passed."""
    if not view or not view.get("flow"):
        return [Content.styled(NO_FLOW, "$clank-quiet")]
    files = view.get("deliverables") or []
    if not files:
        return [Content.styled("nothing written yet", "$clank-quiet")]
    longest = min(max(len(str(each["path"])) for each in files), max(width // 2, 8))
    lines = []
    for each in files:
        where = f"{each['box']}" + (f", try {each['try']}" if each.get("try") else "")
        passed = each.get("passed")
        check: tuple[str, str] = (
            (f"  {mark('done')} its check passed", "$clank-good") if passed
            else (f"  {mark('failed')} its check failed", "$clank-failed") if passed is False
            else ("", "")
        )  # fmt: skip
        gone = ("  not in the folder now", "$clank-attention") if not each.get("present", True) else ("", "")
        lines.append(_fit(Content.assemble((cut(str(each["path"]), longest).ljust(longest), "bold"),
                                           (f"  {where}", "$clank-quiet"), check, gone), width))  # fmt: skip
    return lines


def ahead(view: Mapping[str, Any] | None, width: int) -> list[Content]:
    """Ahead: each box still to run, with what it costs."""
    if not view or not view.get("flow"):
        return [Content.styled(NO_FLOW, "$clank-quiet")]
    boxes = {box["id"]: box for box in view.get("boxes") or []}
    lines = []
    for each in view.get("ahead") or []:
        box = boxes.get(each["box"])
        if box is None:
            continue
        costs = " · ".join(each.get("costs") or [])
        tone = "$clank-attention" if "asks you" in costs else "$clank-quiet"
        lines.append(_fit(Content.assemble(_tagged(box), (f"  {costs}", tone)), width))
    return lines or [Content.styled("nothing: every box has run", "$clank-quiet")]


class DeliverablesList(ListView):
    """The Deliverables panel's files, one a row (design 0013 §12: Enter opens one, `o` in Clank's VS Code window); its
    rows are the panel's lines, cut by the list with "…" where the panel is narrower."""

    DEFAULT_CSS = """
    DeliverablesList {
        height: auto;
        max-height: 12;
    }
    DeliverablesList > ListItem Label {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.files: list[Mapping[str, Any]] = []

    def show(self, view: Mapping[str, Any] | None) -> None:
        """Show the files the flow wrote, the highlight kept on its file."""
        self.files = list((view or {}).get("deliverables") or [])
        kept = self.highlighted()
        keys = [f"{each['box']}/{each['path']}" for each in self.files]
        refill(self, deliverables(view, WIDE) if self.files else [], keys,
               f"{kept['box']}/{kept['path']}" if kept else None)  # fmt: skip
        self.display = bool(self.files)

    def highlighted(self) -> Mapping[str, Any] | None:
        """The file highlighted, the first when none is."""
        if not self.files:
            return None
        index = self.index if self.index is not None and 0 <= self.index < len(self.files) else 0
        return self.files[index]


class LinesView(Static):
    """A panel's lines, from a function of its width: drawn again only when they changed."""

    DEFAULT_CSS = """
    LinesView {
        height: auto;
        width: 1fr;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.making: Callable[[int], Sequence[Content]] = lambda width: []
        self.draws = 0
        self._drawn = ""

    def show(self, making: Callable[[int], Sequence[Content]]) -> None:
        """Draw what `making` gives for the panel's width (and again whenever the width changes)."""
        self.making = making
        self._draw()

    def on_resize(self, event: events.Resize) -> None:
        """Draw again for the new width."""
        self._draw()

    def _draw(self) -> None:
        width = self.content_size.width or WIDTH
        shown = Content("\n").join(self.making(width))
        if shown.markup != self._drawn:
            self._drawn = shown.markup
            self.draws += 1
            self.update(shown)
