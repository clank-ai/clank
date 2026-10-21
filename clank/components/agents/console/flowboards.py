"""The boards of the Flow view beside board D1 (design 0013 §12): what they show, each a function of what the service
says of the flow (`GET /flows/view`) and the width, returning lines no wider than it (decision 0045).

**Board D4, proposals** (`Enter` on a DECOMPOSE while its proposals wait; revised 2026-10-18 at the owner's comment on
the prototype: "a simple list like this is difficult to deal with"): **The flow so far** (`chain`: the flow's boxes in
the order they run, a line of marks, the proposals dashed); the proposals as **cards side by side, in the order they
will run** (`cards`), each titled with its place and its code ("1 · TASK T1?"), its state in its border (to decide:
dashed in the proposals' color; accepted: solid in `good`; rejected: dim, its title struck), its model (and the switch
it needs), what it sees (its own files, then what the tasks before it deliver: tasks run one at a time, each handed
those before it), its deliverable, what to accept, its own keys and when it runs; the highlighted card's whole drafted
prompt (`prompt`); and **How it proposed them** (`calls`: the model's `flow_propose_box` calls and its `flow_submit`).
Cards wrap into rows when the panel is narrower than they are wide together, and never touch (`CARD_GAP`).

**Board D2, a box's settings** (`e`): the flow as a list on the left (`boxchart.listed`, the box edited lit, a box
with a change not saved marked); the box's settings on the right (`settings`): its state and how a change applies now,
then each field with its key (`FIELDS`), its value as it will be saved, a change marked not saved until `s` saves it.

**Board D3, a gate** (`Enter` on a gate): **Where the flow is** (the flow as a list, the gate chosen); what it shows
(`shown`: its first file as the newest try of the box that wrote it kept it, who wrote it and when, how much it changed
since the try before); **VERIFY's report** (`report`: the newest verdict of the VERIFY that checked that box, what it
saw, and what the tries before found); **Against the brief** (the brief, checked); and **Your decision** (`decision`:
each answer with its key and what it does, or that the gate does not wait for you now).
"""

from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

from rich.cells import cell_len
from textual.content import Content

from clank.components.agents.console.boxchart import TAGS, TONES, Canvas, Chart, Rect, corners, tag
from clank.components.agents.console.flowchart import cut
from clank.components.agents.console.flowpanels import after
from clank.console.style import current, mark
from clank.console.text import clock, parse

SHOWN_LINES = 14  # the lines of a file a gate shows, at most (e opens it whole)
CARD_LEAST = 30  # columns a card keeps at least; a row holds as many as keep it
CARD_MOST = 44  # columns a card takes at most
CARD_GAP = 2  # columns between two cards, rows between two rows of them
CARD_ROWS = 10  # a card's rows: its border, its head, title, model, sees, writes, accept, keys, when
LABEL = 8


def _states(view: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    proposals = view.get("proposals") or {}
    items = [dict(each) for each in proposals.get("items") or []]
    live = [str(each["id"]) for each in items if each["state"] != "rejected"]
    return items, live


def counts(view: Mapping[str, Any] | None) -> str:
    """How many proposals wait, were accepted and were rejected."""
    items, _ = _states(view or {})
    said = {state: sum(1 for each in items if each["state"] == state) for state in ("proposed", "accepted", "rejected")}
    return f"{said['proposed']} proposed · {said['accepted']} accepted · {said['rejected']} rejected"


def chain(view: Mapping[str, Any] | None, width: int) -> list[Content]:
    """The flow so far, in the order its boxes run: each with its state's mark and its type, the proposals dashed; then
    what the marks say."""
    if not view or not view.get("flow"):
        return [Content.styled("no flow yet", "$clank-quiet")]
    arrow = current().tree.arrow
    items: list[Content] = []
    for box in view.get("boxes") or []:
        state = box["state"]
        sign = {"done": (mark("done"), "$clank-good"), "running": (mark("on"), "$clank-now"),
                "failed": (mark("failed"), "$clank-failed")}.get(state, (mark("off"), "$clank-quiet"))  # fmt: skip
        if state == "proposed":
            items.append(Content.styled(f"┄{box['id']}?┄", "$clank-box-decompose"))
        else:
            items.append(Content.assemble((f"{sign[0]} ", sign[1]), (tag(box), TONES.get(str(box["type"]), ""))))
    if view.get("next_flow"):
        items.append(Content.styled("next flow", "$clank-quiet"))
    lines: list[Content] = []
    line = Content("")
    for item in items:
        piece = Content.assemble(f" {arrow} ", item) if line.cell_length else item
        if line.cell_length and line.cell_length + piece.cell_length > width:
            lines.append(line)
            line = item
        else:
            line = Content.assemble(line, piece)
    lines.append(line)
    tree = current().tree
    lines.append(Content(""))
    legend = Content.assemble((f"{mark('done')} done  {mark('off')} waiting  ", "$clank-quiet"),
                              (tree.not_yet * 2, "$clank-box-decompose"),
                              (" proposed: not in the flow until you accept it", "$clank-quiet"))  # fmt: skip
    lines.append(_fit(legend, width))
    return lines


def _fit(line: Content, width: int) -> Content:
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)


def cards(view: Mapping[str, Any] | None, width: int, highlighted: str = "") -> Chart:
    """The proposals as cards side by side, in the order they will run, wrapped into rows; the card `highlighted` on
    the selection color. `Chart.boxes` holds each card's rectangle, `Chart.order` the cards in order."""
    chart = Chart(width=max(width, 1), box_rows=CARD_ROWS)
    items, live = _states(view or {})
    if not items:
        canvas = Canvas(chart.width)
        canvas.put(0, 0, cut("no proposal waits: the model proposes boxes as a DECOMPOSE works", width), "$clank-quiet")
        return canvas.chart(chart)
    per_row = max(1, (width + CARD_GAP) // (CARD_LEAST + CARD_GAP))
    card_w = min(CARD_MOST, (width - (per_row - 1) * CARD_GAP) // per_row)
    canvas = Canvas(chart.width)
    models = {each["preset"]: each for each in (view or {}).get("models") or []}
    writes = {str(each["id"]): list(each.get("writes") or []) for each in items}
    for index, item in enumerate(items):
        row, column = divmod(index, per_row)
        rect = Rect(column * (card_w + CARD_GAP), row * (CARD_ROWS + CARD_GAP // 2 + 1), card_w, CARD_ROWS)
        chart.boxes[str(item["id"])] = rect
        chart.order.append(str(item["id"]))
        before = live[: live.index(item["id"])] if item["id"] in live else []
        _card(canvas, rect, index + 1, item, before, writes, models, lit=item["id"] == highlighted)
    return canvas.chart(chart)


def _card(
    canvas: Canvas,
    rect: Rect,
    place: int,
    item: Mapping[str, Any],
    before: list[str],
    writes: Mapping[str, list[str]],
    models: Mapping[str, Mapping[str, Any]],
    *,
    lit: bool,
) -> None:
    """One card: its border by its state, its lines one cell in from its left side."""
    state = str(item["state"])
    kind, color = {"accepted": ("solid", "$clank-good"), "rejected": ("dashed", "$clank-dim")}.get(
        state, ("dashed", "$clank-box-decompose")
    )
    sides = corners(kind)
    on = " on $clank-selection" if lit else ""
    inner = rect.w - 3
    struck = "strike " if state == "rejected" else ""
    code = f"{TAGS.get(str(item['type']), str(item['type']).upper())} {item['id']}{'' if state != 'proposed' else '?'}"
    sign = {"accepted": f"{mark('done')} accepted", "rejected": f"{mark('failed')} rejected"}.get(
        state, f"{mark('note')} edited" if item.get("edited") else "proposed"
    )
    sign_tone = {"accepted": "$clank-good", "rejected": "$clank-failed"}.get(
        state, "$clank-attention" if item.get("edited") else "$clank-box-decompose"
    )
    head = cut(f"{place} · {code}", max(inner - cell_len(sign) - 1, 1))
    model = models.get(str(item.get("preset") or ""), {})
    switch = "" if not model or model.get("loaded") else " · a switch first"
    sees = list(item.get("sees") or [])
    handed = [f"{name}'s {', '.join(writes.get(name) or [])}" for name in before if writes.get(name)]
    when = (
        "not added"
        if state == "rejected"
        else "in the flow"
        if state == "accepted"
        else ("runs first" if not before else f"runs after {before[-1]}")
    )
    lines: list[list[tuple[str, str]]] = [
        [(head, f"bold {TONES.get(str(item['type']), '$clank-text')}"),
         (" " * max(inner - cell_len(head) - cell_len(sign), 1), ""), (sign, sign_tone)],
        [(cut(str(item["title"]), inner), f"{struck}{'bold $clank-selected-text' if lit else '$clank-text'}".strip())],
        _labeled("model", str(item.get("preset_title") or "the flow's model") + switch, inner),
        _labeled("sees", ", ".join([*sees, *handed]) or "the brief", inner),
        _labeled("writes", ", ".join(item.get("writes") or []) or "nothing", inner),
        _labeled("accept", "; ".join(item.get("accept_when") or []) or "you decide at the gate", inner),
        [(cut("a accept  e edit  r reject", inner), "$clank-quiet")],
        [(cut(when, inner), "$clank-quiet")],
    ]  # fmt: skip
    x, y, w = rect.x, rect.y, rect.w
    canvas.put(x, y, sides[0] + sides[4] * (w - 2) + sides[1], color)
    for row in range(1, rect.h - 1):
        canvas.put(x, y + row, sides[5], color)
        canvas.put(x + 1, y + row, " " * (w - 2), on.strip())
        at = x + 2
        for text, style in lines[row - 1] if row - 1 < len(lines) else []:
            at = canvas.put(at, y + row, text, f"{style}{on}".strip())
        canvas.put(x + w - 1, y + row, sides[5], color)
    canvas.put(x, y + rect.h - 1, sides[2] + sides[4] * (w - 2) + sides[3], color)


def _labeled(label: str, value: str, inner: int) -> list[tuple[str, str]]:
    return [(f"{label:<{LABEL}}", "$clank-quiet"), (cut(value, max(inner - LABEL, 1)), "$clank-text")]


def prompt(view: Mapping[str, Any] | None, highlighted: str, width: int) -> list[Content]:
    """The highlighted card's whole drafted prompt: its first message's own words, wrapped to the width."""
    items, _ = _states(view or {})
    item = next((each for each in items if each["id"] == highlighted), None)
    if item is None:
        return [Content.styled("no card highlighted: the arrows move between them", "$clank-quiet")]
    said = "the prompt, edited by you" if item.get("edited") else "drafted prompt: the task session's first message"
    lines = [Content.styled(f"{item['id']} · {said} (e edits it)", "bold $clank-quiet")]
    for paragraph in str(item.get("prompt") or "").splitlines() or [""]:
        lines += [Content(row) for row in _wrap(paragraph, width)]
    if item.get("why"):
        lines.append(Content.assemble(("why: ", "$clank-quiet"), str(item["why"])))
    return [_fit(line, width) for line in lines]


def _wrap(text: str, width: int) -> list[str]:
    """Words in lines no wider than the width (a word longer than a line is cut)."""
    lines: list[str] = []
    line = ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if cell_len(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = cut(word, width)
    lines.append(line)
    return lines


def calls(view: Mapping[str, Any] | None, width: int, zone: tzinfo | None) -> list[Content]:
    """How it proposed them: the model's calls to Clank's MCP server, in order, and what became of each; its
    `flow_submit`; that the model only proposes, and the flow's auto-accept."""
    proposals = (view or {}).get("proposals") or {}
    items = proposals.get("items") or []
    if not items:
        return [Content.styled("no call yet", "$clank-quiet")]
    when = clock(parse(items[0]["given"]), zone) if items[0].get("given") else ""
    lines = [Content.styled(f"{proposals.get('box')}'s calls to Clank's MCP server{', ' + when if when else ''}",
                            "$clank-quiet")]  # fmt: skip
    for each in items:
        call = f"flow_propose_box(after={each['after']}, type={str(each['type']).upper()}, title=…)"
        said = Content.assemble((call, "$clank-quiet"), " → ", (str(each["id"]), "bold"), f" {each['title']} ")
        lines.append(_fit(Content.assemble(said, (str(each["state"]), "$clank-quiet")), width))
    if proposals.get("submitted"):
        summary = f" · {proposals['summary']}" if proposals.get("summary") else ""
        lines.append(_fit(Content.assemble((f"flow_submit({len(items)} boxes)", "$clank-quiet"), summary), width))
    settings = (view or {}).get("settings") or {}
    auto = "on, up to " + str(settings.get("auto_accept_cap")) if settings.get("auto_accept") else "off"
    lines.append(_fit(Content.styled(f"The model only proposes; you decide. Auto-accept is {auto} for this flow.",
                                     "$clank-quiet"), width))  # fmt: skip
    return lines


# Board D3, a gate.


def gate_files(view: Mapping[str, Any] | None, gate: str) -> list[dict[str, Any]]:
    """The files a gate shows, each with the box that wrote it and the newest try of that box that wrote it."""
    boxes = {box["id"]: box for box in (view or {}).get("boxes") or []}
    found = []
    for each in (boxes.get(gate) or {}).get("shown") or []:
        writer = boxes.get(each["box"]) or {}
        tries = [one["number"] for one in writer.get("tries") or [] if each["path"] in (one.get("written") or [])]
        found.append({"path": each["path"], "box": each["box"], "tries": tries})
    return found


def checker(view: Mapping[str, Any] | None, box: str) -> Mapping[str, Any] | None:
    """The VERIFY that checks a box, the last in the order they run."""
    found = [each for each in (view or {}).get("boxes") or [] if each["type"] == "verify" and each.get("checks") == box]
    return found[-1] if found else None


def shown(
    view: Mapping[str, Any] | None, gate: str, copy: Mapping[str, Any] | None, width: int, zone: tzinfo | None
) -> list[Content]:
    """What the gate shows: its first file as its box's newest try kept it, who wrote it and when, and how much it
    changed since the try before."""
    files = gate_files(view, gate)
    if not files:
        return [Content.styled("this gate shows no file: it asks you to go on", "$clank-quiet")]
    first = files[0]
    boxes = {box["id"]: box for box in (view or {}).get("boxes") or []}
    writer = boxes.get(first["box"]) or {}
    if not first["tries"]:
        return [Content.styled(f"{first['path']} is not written yet", "$clank-quiet")]
    number = first["tries"][-1]
    made = next(each for each in writer["tries"] if each["number"] == number)
    when = clock(parse(made["ended"]), zone) if made.get("ended") else ""
    by = f"{tag(writer)}, try {number}" + (f" · {writer.get('preset_title')}" if writer.get("preset_title") else "")
    lines = [Content.styled(f"written {when} by {by}".replace("written  by", "written by"), "$clank-quiet")]
    copy = copy or {}
    text = copy.get("text")
    if text is None:
        lines.append(Content.styled(str(copy.get("why") or "reading its copy"), "$clank-quiet"))
    else:
        rows = str(text).splitlines()
        lines += [Content(cut(row, width)) for row in rows[:SHOWN_LINES]]
        if len(rows) > SHOWN_LINES:
            lines.append(Content.styled(f"and {len(rows) - SHOWN_LINES} lines more: e opens it whole", "$clank-quiet"))
    if copy.get("changed") is not None and copy.get("a"):
        changed = int(copy["changed"])
        said = f"changed since try {copy['a']}: {changed} line{'s' if changed != 1 else ''} · d shows the difference"
        lines.append(Content.styled(f"▎ {said}", "$clank-attention"))
    return [_fit(line, width) for line in lines]


def report(view: Mapping[str, Any] | None, gate: str, width: int, zone: tzinfo | None) -> list[Content]:
    """The report of the VERIFY that checked what the gate shows: its newest verdict, what it saw, and what each try
    before it found."""
    files = gate_files(view, gate)
    boxes = {box["id"]: box for box in (view or {}).get("boxes") or []}
    checked = files[0]["box"] if files else ""
    verify = checker(view, checked)
    if verify is None:
        named = tag(boxes[checked]) if checked in boxes else "it"
        return [Content.styled(f"no VERIFY checks {named}: what it shows is yours to judge", "$clank-quiet")]
    given = [(each["number"], each["verdict"]) for each in verify.get("tries") or [] if each.get("verdict")]
    if not given:
        return [Content.styled(f"{verify['title']} has given no verdict yet", "$clank-quiet")]
    number, verdict = given[-1]
    passed = verdict["result"] == "pass"
    sign, tone = (mark("done"), "$clank-good") if passed else (mark("failed"), "$clank-failed")
    when = clock(parse(verdict["given"]), zone) if verdict.get("given") else ""
    fresh = f" · {verify.get('preset_title')} in a fresh session" if verify.get("preset_title") else ""
    lines = [Content.assemble((f"{sign} {verdict['result']} (try {number})", f"bold {tone}"), f" {when}{fresh}")]
    seen = [str(each) for each in verify.get("sees") or []]
    sees = (
        ", ".join(seen[:-1]) + f" and {seen[-1]}"
        if len(seen) > 1
        else (seen[0] if seen else "the brief and the deliverable")
    )
    named = tag(boxes[checked]) if checked in boxes else checked
    lines.append(Content.styled(f"It saw only {sees}, not {named}'s session.", "$clank-quiet"))
    for earlier, found in given[:-1]:
        if found["result"] == "fail":
            count = len(found.get("findings") or [])
            lines.append(Content(f"Try {earlier} found {count} thing{'s' if count != 1 else ''}:"))
            lines += [Content.assemble((f"{index}  ", "$clank-failed"), str(finding))
                      for index, finding in enumerate(found.get("findings") or [], start=1)]  # fmt: skip
    if not passed:
        lines.append(Content(f"It found {len(verdict.get('findings') or [])} things:"))
        lines += [Content.assemble((f"{index}  ", "$clank-failed"), str(finding))
                  for index, finding in enumerate(verdict.get("findings") or [], start=1)]  # fmt: skip
    return [_fit(line, width) for line in lines]


ANSWER_KEYS = {"approve": "a", "go": "a", "back": "s", "retry": "r", "take": "t", "skip": "k", "stop": "x"}


def asked(view: Mapping[str, Any] | None, gate: str) -> Mapping[str, Any] | None:
    """The question the flow waits for at a box, with its answers; None when it waits for none there."""
    return next((each for each in (view or {}).get("waiting") or [] if each["box"] == gate), None)


def answers(view: Mapping[str, Any] | None, gate: str) -> dict[str, str]:
    """The keys of the answers the question at a gate offers, each to its option's id: `a` the go-ahead (approve, or
    go on), `s` send back, `x` stop, and the others by their first letter; `e` (edit, then approve) with approve."""
    found: dict[str, str] = {}
    for option in (asked(view, gate) or {}).get("options") or []:
        key = ANSWER_KEYS.get(str(option["id"]))
        if key and key not in found:
            found[key] = str(option["id"])
    if "approve" in found.values():
        found["e"] = "approve"
    return found


def decision(view: Mapping[str, Any] | None, gate: str, width: int) -> list[Content]:
    """The answers of the question the gate waits for, each with its key and what it does (an approval's, a send
    back's, or the go on or stop of a flow that waits after every box); or that the gate does not wait for you now."""
    boxes = {box["id"]: box for box in (view or {}).get("boxes") or []}
    box = boxes.get(gate) or {}
    files = gate_files(view, gate)
    question = asked(view, gate)
    if question is None:
        state = {"done": "approved", "waiting": "not reached yet"}.get(str(box.get("state")), str(box.get("state")))
        lines = [Content.styled(f"This gate does not wait for you now: it is {state}.", "$clank-quiet")]
        if files:
            lines.append(_key("d", "Diff with the try before", ""))
        return [_fit(line, width) for line in lines]
    following = [boxes[name] for name in box.get("next") or [] if name in boxes]
    after = f"next: {tag(following[0])} {following[0]['title']}" if following else "the flow ends here"
    path = files[0]["path"] if files else "the file"
    writer = boxes.get(files[0]["box"]) if files else None
    back = tag(writer) if writer else "the box before it"
    if writer:
        used, cap = len(writer.get("tries") or []), writer.get("cap") or 0
        verify = checker(view, writer["id"])
        again = f"; {tag(verify)} checks it again" if verify else ""
        then = (f"{back} writes try {used + 1} of {cap} with your note{again}" if used < cap
                else f"{back} writes try {used + 1}, past its {cap}, with your note{again}")  # fmt: skip
    else:
        then = "the box before it runs again with your note"
    lines = []
    for option in question.get("options") or []:
        id, key = str(option["id"]), ANSWER_KEYS.get(str(option["id"]), "")
        if id == "approve":
            lines.append(_key("a", str(option["label"]), after))
            lines.append(_key("e", f"Edit {path}, then approve",
                              "it opens in Clank's VS Code window; a approves once you saved it"))  # fmt: skip
        elif id == "back":
            lines.append(_key("s", f"Send back to {back} with a note", then))
        elif id == "go":
            lines.append(_key("a", str(option["label"]), f"{after}; the flow waits after every box"))
        elif key:
            lines.append(_key(key, str(option["label"]), str(option.get("effect") or "")))
    lines.append(_key("d", "Diff with the try before", ""))
    lines.append(Content.styled("Also on your phone: answer it from there.", "$clank-quiet"))
    return [_fit(line, width) for line in lines]


def _key(key: str, does: str, then: str) -> Content:
    return Content.assemble(
        (f"{key}  ", "bold $clank-key"), (does, "bold"), (f"   {then}" if then else "", "$clank-quiet")
    )


# Board D2, a box's settings.

FIELDS = (
    ("t", "type", "Type"),
    ("m", "model", "Model"),
    ("o", "mode", "Mode"),
    ("i", "sees", "Sees"),
    ("p", "prompt", "Prompt"),
    ("d", "writes", "Deliverable"),
    ("a", "accept_when", "Accept when"),
    ("n", "when_done", "When done"),
    ("r", "tries", "Tries"),
    ("l", "limits", "Limits"),
    ("u", "mcp_servers", "Tools"),
    ("w", "network", "Network"),
)  # board D2's fields, each with its key, in its order
FIELD_LABEL = 13
MODE_WORDS = {
    "plan": "plan: Markdown only",
    "review": "review: changes wait for you",
    "auto": "auto: changes accepted at once",
}


def settings(
    view: Mapping[str, Any] | None,
    box: Mapping[str, Any],
    values: Mapping[str, Any],
    changed: set[str],
    now: Mapping[str, Any] | None,
    width: int,
    zone: tzinfo | None,
) -> list[Content]:
    """A box's settings (board D2): its state and how a change applies now, then each field with its key and its
    value as it will be saved (`values`, the box's file with the changes not saved yet), a change marked not saved,
    and how many wait for `s`."""
    boxes = {each["id"]: each for each in (view or {}).get("boxes") or []}
    defaults = ((view or {}).get("defaults")) or {}
    lines: list[Content] = [
        _fit(_state_line(box, now, zone), width),
        _fit(Content.styled(_applies(box), "$clank-quiet"), width),
        Content(""),
    ]
    for key, field, label in FIELDS:
        said = _field(field, box, values, boxes, view or {}, defaults)
        mark_ = (f"  {mark('note')} not saved", "$clank-attention") if field in changed else ("", "")
        line = Content.assemble(
            (f"{key}  ", "bold $clank-key"), (f"{label:<{FIELD_LABEL}}", "$clank-quiet"), said, mark_
        )
        if line.cell_length > width and field in changed:  # the mark is kept: the value is cut first
            room = width - cell_len(mark_[0]) - 3 - FIELD_LABEL
            line = Content.assemble((f"{key}  ", "bold $clank-key"), (f"{label:<{FIELD_LABEL}}", "$clank-quiet"),
                                    _fit(said, max(room, 1)), mark_)  # fmt: skip
        lines.append(_fit(line, width))
    lines.append(Content(""))
    if changed:
        names = ", ".join(label for _, field, label in FIELDS if field in changed)
        count = len(changed)
        said_ = (
            f"{mark('note')} {count} change{'s' if count != 1 else ''} not saved: {names}. s saves it; Esc leaves it."
        )
        lines.append(_fit(Content.styled(said_, "$clank-attention"), width))
    lines.append(
        _fit(
            Content.styled(
                "v shows the whole first message: this prompt, the files it sees, its tools.", "$clank-quiet"
            ),
            width,
        )
    )
    return lines


def _state_line(box: Mapping[str, Any], now: Mapping[str, Any] | None, zone: tzinfo | None) -> Content:
    state = str(box["state"])
    tries = box.get("tries") or []
    if state == "running" and tries:
        started = clock(parse(tries[-1]["started"]), zone)
        found = now or {}
        speed = (found.get("speed") or {}).get("now")
        parts = [f"running since {started}"]
        if found.get("step"):
            parts.append(f"step {found['step']}")
        if speed:
            parts.append(f"{speed:.0f} tokens a second")
        return Content.assemble((f"{mark('on')} ", "$clank-now"), " · ".join(parts))
    if state == "done":
        when = clock(parse(box["ended"]), zone) if box.get("ended") else ""
        return Content.assemble((f"{mark('done')} ", "$clank-good"), f"done {when}".strip())
    if state == "failed":
        return Content.assemble((f"{mark('failed')} ", "$clank-failed"), f"failed: {box.get('why') or ''}".rstrip(": "))
    return Content.assemble((f"{mark('off')} ", "$clank-quiet"), str(state))


def _applies(box: Mapping[str, Any]) -> str:
    state = str(box["state"])
    if state == "running":
        return "It is running: a change here applies from its next try."
    if state in ("done", "stale", "failed", "skipped"):
        return "Changing a finished box marks every box after it stale; nothing reruns on its own."
    return "A change to a box that has not started applies when it starts."


def _field(
    field: str,
    box: Mapping[str, Any],
    values: Mapping[str, Any],
    boxes: Mapping[str, Mapping[str, Any]],
    view: Mapping[str, Any],
    defaults: Mapping[str, Any],
) -> Content:
    """One field's value as it will be saved, in words."""
    kind = str(values.get("type") or box["type"])
    owner = kind in ("you", "gate")
    if field == "type":
        proposed = values.get("proposed") or {}
        accepted = "you" if proposed.get("accepted", "owner") == "owner" else "auto-accept"
        by = f" · proposed by {proposed['by']}, accepted by {accepted}" if proposed else ""
        return Content.assemble(
            (TAGS.get(kind, kind.upper()), f"bold {TONES.get(kind, '$clank-text')}"), (by, "$clank-quiet")
        )
    if field == "model":
        if owner:
            return Content.styled("you", "$clank-quiet")
        named = str(values.get("model") or "")
        title = named or str(box.get("preset_title") or "main slot's model")
        loaded = next(
            (
                each.get("loaded")
                for each in view.get("models") or []
                if each.get("title") == title or each.get("preset") == named
            ),
            False,
        )
        whose = "" if named else " (the flow's)"
        then = " · loaded now" if loaded else " · another preset loads before this box starts"
        return Content.assemble(title + whose, (then, "$clank-quiet"))
    if field == "mode":
        if owner:
            return Content.styled("you", "$clank-quiet")
        mode = values.get("mode")
        if mode:
            return Content(MODE_WORDS.get(str(mode), str(mode)))
        own = "plan" if kind in ("plan", "verify", "decompose", "integrate") else ""
        return Content.assemble(
            MODE_WORDS[own] if own else "the workspace's", (" (its type's)" if own else "", "$clank-quiet")
        )
    if field == "sees":
        files = ", ".join(values.get("shows" if kind == "gate" else "sees") or [])
        return Content.assemble(
            files or "the brief", (" · not the whole history: a fresh session" if not owner else "", "$clank-quiet")
        )
    if field == "prompt":
        prompt = str(values.get("prompt") or "").strip().splitlines()
        return Content(prompt[0]) if prompt else Content.styled("none", "$clank-quiet")
    if field == "writes":
        files = ", ".join(values.get("writes") or []) or "nothing"
        holds = str(values.get("holds") or "")
        return Content.assemble(files, (f" · {holds}" if holds else "", "$clank-quiet"))
    if field == "accept_when":
        lines = [str(each) for each in values.get("accept_when") or []]
        checked = [each for each in boxes.values() if each["type"] == "verify" and each.get("checks") == box["id"]]
        by = f" · checked by {tag(checked[-1])}" if checked else " · checked by you, at a gate"
        return Content.assemble("; ".join(lines) or "not said", (by, "$clank-quiet"))
    if field == "when_done":
        if values.get("when_done") == "wait":
            return Content("wait for you")
        following = after(boxes, box)
        return Content(f"go on to {tag(following[0])}" if following else "go on")
    if field == "tries":
        if owner:
            return Content.styled("you decide", "$clank-quiet")
        cap = values.get("tries") or defaults.get("tries") or box.get("cap") or 3
        now = f" · this is try {len(box['tries'])}" if box["state"] == "running" and box.get("tries") else ""
        return Content.assemble(f"up to {cap}, then a gate decides", (now, "$clank-quiet"))
    if field == "limits":
        if owner:
            return Content.styled("none: it waits for you", "$clank-quiet")
        limits = dict(box.get("limits") or {})
        given = values.get("limits") or {}
        limits |= {key: value for key, value in given.items() if value}
        minutes, tokens = limits.get("minutes"), limits.get("tokens")
        return Content(f"{minutes} minutes, {int(tokens or 0):,} tokens")
    if field == "mcp_servers":
        servers = values.get("mcp_servers")
        if servers is None:
            return Content.assemble("bash · read · edit", (" · the workspace's agent's MCP servers", "$clank-quiet"))
        return Content("bash · read · edit · " + " · ".join(servers) if servers else "bash · read · edit")
    return Content.assemble(
        "none", (" · nothing it runs can reach the internet (network grants come with M7)", "$clank-quiet")
    )
