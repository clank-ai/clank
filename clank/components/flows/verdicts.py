"""A VERIFY's verdict (design 0013 §2, §8, §9): *pass*, or *fail* with numbered findings, and the lines it checked.

A VERIFY box ends by calling `flow_verdict` (Clank's MCP server, through the gateway's `/flows/` routes, to the
service), and the service gives the verdict to the VERIFY at work in the workspace (`Runner.verdict`). It is kept on
the VERIFY's try in the run's file, and as `verdict.md` in the try's folder (§8, `text`). `given` checks what the model
sent, each refusal saying what to fix: the result is pass or fail; a fail lists its findings, each one thing to fix
(numbered in their order); each criterion is an object of its line, whether it is met (true or false; the words yes,
no, met and not met read as such) and its evidence, and a refusal names the criterion and the field to fix. A pass
may carry findings too, kept as remarks. `criteria`
are the lines of the brief's limits and of what the deliverable is accepted when that the check touched, each met or
not, with its evidence (§9, as revised for §12's **The brief, checked**); a line no verdict names stays "not checked
yet" there.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from clank.kernel.events import Actor

AGENT = Actor(kind="session", via="the agent")  # who gives a verdict through the gateway
Result = Literal["pass", "fail"]
SAID_MET = {"true": True, "yes": True, "met": True, "false": False, "no": False, "not met": False}  # `met` in words


class VerdictRefused(ValueError):
    """A verdict that cannot be kept as sent, and what to fix."""


class Criterion(BaseModel):
    """A line the check touched: met or not, and what shows it."""

    model_config = ConfigDict(extra="forbid")

    line: str = Field(
        description="A line of the brief's limits, or of what the deliverable is accepted when, as the check quotes it."
    )
    met: bool = Field(description="Whether the deliverable meets it.")
    evidence: str = Field("", description="What shows it: a figure, a line, a file.")


class Verdict(BaseModel):
    """A VERIFY's verdict on the deliverable of the box it checks."""

    model_config = ConfigDict(extra="forbid")

    result: Result = Field(description="pass, or fail.")
    findings: list[str] = Field(
        default_factory=list,
        description="A fail's findings, each one thing to fix, numbered from 1 in this order; a pass's are remarks.",
    )
    criteria: list[Criterion] = Field(
        default_factory=list, description="The lines of the brief and of accept when that the check touched."
    )
    checked: int | None = Field(None, description="The try of the checked box it is on.")
    given: datetime = Field(description="When it was given.")
    by: Actor = Field(description="Who gave it: the agent's session, through the gateway.")


def given(
    result: str,
    findings: Sequence[str],
    criteria: Sequence[object],
    *,
    checked: int | None,
    at: datetime,
    by: Actor,
) -> Verdict:
    """The verdict as it is kept; `VerdictRefused`, saying what to fix, when it cannot be. Each criterion is a
    `Criterion`, or as the model sent it (an object of `line`, `met` and `evidence`), read here so that a refusal names
    the criterion and its field."""
    word = result.strip().lower()
    if word not in ("pass", "fail"):
        raise VerdictRefused(f"a verdict is pass or fail, not {result!r}")
    listed = [each.strip() for each in findings if each.strip()]
    if word == "fail" and not listed:
        raise VerdictRefused("a fail lists its findings, each one thing to fix: give your verdict again with them")
    kept = [_criterion(number, each) for number, each in enumerate(criteria, start=1)]
    return Verdict(result=word, findings=listed, criteria=kept, checked=checked, given=at, by=by)


def _criterion(number: int, sent: object) -> Criterion:
    """A criterion as the model sent it, read; `VerdictRefused`, naming it and its field, when it cannot be."""
    fields = sent.model_dump() if isinstance(sent, Criterion) else sent
    if not isinstance(fields, dict):
        raise VerdictRefused(f"criterion {number} is not an object: give each as its line, met and evidence")
    extra = sorted(str(key) for key in fields if key not in Criterion.model_fields)
    if extra:
        raise VerdictRefused(
            f"criterion {number} has {', '.join(extra)}, which a criterion does not take: give its line, met and "
            "evidence, and put the rest in its evidence"
        )
    line = fields.get("line")
    if not isinstance(line, str) or not line.strip():
        raise VerdictRefused(
            f"criterion {number} names no line: quote the line of the brief or of accept when that it checks"
        )
    met = fields.get("met")
    if met is None:
        raise VerdictRefused(f"criterion {number} does not say whether it is met: say true or false")
    if isinstance(met, str) and met.strip().lower() in SAID_MET:
        met = SAID_MET[met.strip().lower()]
    if not isinstance(met, bool):
        raise VerdictRefused(f"criterion {number}'s met is {met!r}: say true or false")
    evidence = fields.get("evidence")
    return Criterion(line=line.strip(), met=met, evidence="" if evidence is None else str(evidence).strip())


def text(verdict: Verdict, *, box: str, title: str, number: int, checks: str) -> str:
    """The verdict as Markdown (`verdict.md`): its result, what it is on, its findings and the lines it checked."""
    on = f"{checks}'s try {verdict.checked}" if verdict.checked else checks
    lines = [
        f"# Verdict: {verdict.result}",
        "",
        f"{title} ({box}), try {number}, on {on}: given {verdict.given.isoformat(timespec='seconds')} by "
        f"{verdict.by.describe()}.",
    ]
    if verdict.findings:
        lines += ["", "## Findings" if verdict.result == "fail" else "## Remarks", ""]
        lines += [f"{index}. {finding}" for index, finding in enumerate(verdict.findings, start=1)]
    if verdict.criteria:
        lines += ["", "## The brief, checked", ""]
        for criterion in verdict.criteria:
            said = f"- {'met' if criterion.met else 'not met'}: {criterion.line}"
            lines.append(f"{said}: {criterion.evidence}" if criterion.evidence else said)
    return "\n".join(lines) + "\n"
