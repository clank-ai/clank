"""What the cloud cost, kept by the service (design 0016 §11-§12, decision 0108): the gateway's spool, taken every two
seconds into the gateway component's table `cloud_costs`, by the spool's run and sequence, so nothing is counted twice.

A request whose stream was cut short has no usage: it comes as an estimate, labeled so, and its cost is asked of the
provider's record of it (its generation) 10 s, 60 s and 5 min after it ended, with the provider's key read through the
kernel; once known, the row is made exact (`how`: `generation`). Each row taken or changed gets the next revision
(`rev`), so a client asks for what changed since the last it saw. A refusal the spool carries (by Clank or by the
provider) is the event `gateway.cloud_refused`, at most one a minute for each workspace and code.
"""

import json
import math
import threading
import time
from contextlib import suppress
from datetime import date, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any

import httpx2

from clank.kernel.clock import from_text, to_text
from clank.kernel.events import Actor, Subject
from clank.kernel.questions import Asked, Option, Question, QuestionDraft, QuestionError

if TYPE_CHECKING:
    from clank.components.gateway.service import Gateway

GATEWAY = Actor(kind="clank", via="gateway")
GENERATION_DELAYS = (10.0, 60.0, 300.0)  # when a stream cut short's cost is asked of its generation, after it ended
REFUSALS_SECONDS = 60.0  # at most one refusal event a minute for each workspace and code
COST_SECONDS = 5.0  # `gateway.cost` at most every five seconds while the totals change
RAISE_MOST = 100_000.0  # the most a raise of a limit may ask, in US dollars
REFUSED_WORDS = {
    "model_send_denied": "kept on this machine",
    "local_only": "its session used local-only content",
    "service_silent": "the Clank service did not answer",
    "key_refused": "the provider refused the key",
    "no_credits": "credits used up, or the key's limit reached",
    "refused": "the provider refused it",
    "no_model": "the provider lists no such model",
    "rate_limited": "a limit of requests",
    "free_limit": "the free models' limit for the day",
    "data_policy": "no provider serves it under the data policy",
}


class Costs:
    """The cloud's costs in the service: taken from the gateway's spool, made exact, read back."""

    def __init__(self, gateway: "Gateway") -> None:
        self.gateway = gateway
        self.kernel = gateway.kernel
        self._lock = threading.Lock()
        self._run = ""  # the spool's run last taken from
        self._asked: dict[int, int] = {}  # each estimate's generation, how many times asked
        self._taken_at: dict[int, datetime] = {}  # when each row was taken, by the service's clock
        self._refused: dict[tuple[str, str], float] = {}  # each workspace and code, when last announced
        self.zone: tzinfo | None = None  # this computer's days (None: the system's zone; a test sets one)
        self._told: tuple[float, ...] = ()  # the totals `gateway.cost` last told
        self._told_at = -COST_SECONDS
        self._warned: set[tuple[str, str]] = set()  # each limit and period the owner was told of at `warn_at`
        self._warning: dict[str, Any] | None = None  # the limit nearly reached now
        self._paused: dict[str, Any] | None = None  # the cloud paused at a limit now
        self.held = 0  # the cloud requests the gateway holds at a limit now, as it last said
        self.kernel.questions.on_resolved(self._resolved)

    def take(self) -> int:
        """Take the spool's new entries into the table (none twice); how many were new."""
        with self._lock:
            taken = self._last(self._run) if self._run else 0
            answer = self.gateway.ask_gateway("GET", "/spend", params={"after": str(taken)})
            found = answer.json()
            run = str(found.get("run") or "")
            if run != self._run:  # a spool of another run (a gateway started anew): what is new of it, from its start
                self._run = run
                if taken:
                    found = self.gateway.ask_gateway("GET", "/spend", params={"after": str(self._last(run))}).json()
            self.held = int(found.get("held") or 0)
            entries = [entry for entry in found.get("entries") or [] if isinstance(entry, dict)]
            added = [entry for entry in entries if self._insert(run, entry)]
        for entry in added:
            self._announce(entry)
        return len(added)

    def price_generations(self) -> int:
        """Ask the provider what each estimate cost, once its time comes (10 s, 60 s and 5 min after it ended); how
        many were made exact."""
        now = self.kernel.clock.now()
        rows = self.kernel.store.read(
            "SELECT id, time, endpoint, generation, request FROM cloud_costs"
            " WHERE how = 'estimate' AND generation != ''"
        )
        made = 0
        for row in rows:
            asked = self._asked.get(row["id"], 0)
            if asked >= len(GENERATION_DELAYS):
                continue
            since = self._taken_at.get(row["id"]) or from_text(row["time"])
            if now - since < timedelta(seconds=GENERATION_DELAYS[asked]):
                continue
            self._asked[row["id"]] = asked + 1
            usd = self._generation_cost(str(row["endpoint"]), str(row["generation"]), str(row["request"]))
            if usd is None:
                continue
            with self.kernel.store.transaction() as db:
                db.execute(
                    "UPDATE cloud_costs SET usd = ?, how = 'generation',"
                    " rev = (SELECT COALESCE(MAX(rev), 0) + 1 FROM cloud_costs) WHERE id = ?",
                    (usd, row["id"]),
                )
            made += 1
        return made

    def requests(
        self, *, session: str = "", workspace: str = "", since: str = "", after: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Each cloud request's cost, newest first: of a session (its subagents' too) or a workspace, since a time, or
        changed after a revision."""
        where: list[str] = ["rev > ?"]
        params: list[Any] = [after]
        if session:
            where.append("(session = ? OR parent = ?)")
            params += [session, session]
        if workspace:
            where.append("workspace = ?")
            params.append(workspace)
        if since:
            where.append("time >= ?")
            params.append(since)
        rows = self.kernel.store.read(
            f"SELECT * FROM cloud_costs WHERE {' AND '.join(where)} ORDER BY time DESC, id DESC LIMIT ?",
            (*params, limit),
        )
        return [_request(row) for row in rows]

    def revision(self) -> int:
        """The newest revision of the costs."""
        return int(self.kernel.store.read("SELECT COALESCE(MAX(rev), 0) FROM cloud_costs")[0][0])

    def _last(self, run: str) -> int:
        rows = self.kernel.store.read("SELECT COALESCE(MAX(seq), 0) FROM cloud_costs WHERE run = ?", (run,))
        return int(rows[0][0])

    def _insert(self, run: str, entry: dict[str, Any]) -> bool:
        with self.kernel.store.transaction() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO cloud_costs (run, seq, time, request, session, parent, workspace, endpoint,"
                " preset, model, generation, tokens, usd, how, status, code, rev) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                " ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(rev), 0) + 1 FROM cloud_costs))",
                (
                    run, int(entry["seq"]), str(entry.get("time") or to_text(self.kernel.clock.now())),
                    str(entry.get("id") or ""), str(entry.get("session") or ""), str(entry.get("parent") or ""),
                    str(entry.get("workspace") or ""), str(entry.get("endpoint") or ""),
                    str(entry.get("preset") or ""), str(entry.get("model") or ""),
                    str(entry.get("generation") or ""), json.dumps(entry.get("tokens") or {}),
                    float(entry.get("usd") or 0.0), _how(entry.get("how")), entry.get("status"),
                    str(entry.get("code") or ""),
                ),
            )  # fmt: skip
            if cursor.rowcount and cursor.lastrowid:
                self._taken_at[int(cursor.lastrowid)] = self.kernel.clock.now()
            return bool(cursor.rowcount)

    def _announce(self, entry: dict[str, Any]) -> None:
        """A refused request, said once a minute for each workspace and code (design 0016 §8-§10)."""
        code = str(entry.get("code") or "")
        if not code or code not in REFUSED_WORDS:
            return
        workspace = str(entry.get("workspace") or "")
        moment = time.monotonic()
        if moment - self._refused.get((workspace, code), -REFUSALS_SECONDS) < REFUSALS_SECONDS:
            return
        self._refused[(workspace, code)] = moment
        whose = f" of {workspace}" if workspace else ""
        self.kernel.events.record(
            "gateway.cloud_refused",
            summary=f"a cloud request{whose} was refused: {REFUSED_WORDS[code]} ({code})",
            actor=GATEWAY,
            subject=Subject(kind="workspace", id=workspace) if workspace else None,
            data={"workspace": workspace, "session": str(entry.get("session") or ""), "code": code,
                  "status": entry.get("status")},
        )  # fmt: skip

    def _generation_cost(self, endpoint: str, generation: str, request: str) -> float | None:
        """A request's cost from the provider's record of it; None while it has none, or it does not answer."""
        from clank.kernel.api import ApiError

        endpoints = self.gateway.runtime.endpoints
        try:
            key = endpoints.key(endpoint, user="gateway", why=f"the cost of request {request}")
            answer = endpoints.ask(endpoint, key, "GET", "/generation", params={"id": generation})
        except (ApiError, httpx2.HTTPError):
            return None
        if answer.status_code != 200:
            return None
        try:
            return endpoints.adapter(endpoint).generation_cost(answer.json())
        except (ValueError, ApiError):
            return None

    # The views every client reads (design 0016 §11): this computer's days and months, raw numbers and their words.

    def keep_entries(self, run: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep a spool's entries (each once, by its run and sequence); those that were new."""
        added = [entry for entry in entries if self._insert(run, entry)]
        for entry in added:
            self._announce(entry)
        return added

    def periods(self) -> dict[str, dict[str, Any]]:
        """Today and this month in this computer's days (`zone`, else the system's): each period's bounds as Clank's
        UTC times, each at the offset of its own moment (a day the clocks change is 23 or 25 hours long), and its local
        name."""
        today = self._here().date()
        first = today.replace(day=1)
        following = (first + timedelta(days=32)).replace(day=1)
        return {
            "today": {"from": self._midnight(today), "until": self._midnight(today + timedelta(days=1)),
                      "local": today.isoformat()},
            "month": {"from": self._midnight(first), "until": self._midnight(following),
                      "local": first.strftime("%Y-%m")},
        }  # fmt: skip

    def _here(self) -> datetime:
        """Now, in this computer's days."""
        now = self.kernel.clock.now()
        return now.astimezone(self.zone) if self.zone else now.astimezone()

    def _midnight(self, day: date) -> str:
        """A day's start in this computer's days, as Clank's UTC time: at the offset of that moment, by the zone's
        rules (the system's, for a time without a zone, with its own changes of the clock)."""
        wall = datetime(day.year, day.month, day.day)
        return to_text(wall.replace(tzinfo=self.zone) if self.zone else wall.astimezone())

    def totals(self, since: str, until: str, workspace: str = "") -> dict[str, Any]:
        """What the cloud cost from `since` to before `until`: its requests', and the runtime's own (a load's health, a
        check, a test); how many requests went; the part still an estimate. Of one workspace (`workspace`): its
        requests' alone."""
        mine = " AND workspace = ?" if workspace else ""
        row = self.kernel.store.read(
            "SELECT COALESCE(SUM(usd), 0) AS usd, COALESCE(SUM(CASE WHEN how = 'estimate' THEN usd ELSE 0 END), 0)"
            " AS estimated, COALESCE(SUM(CASE WHEN code = '' THEN 1 ELSE 0 END), 0) AS requests"
            f" FROM cloud_costs WHERE time >= ? AND time < ?{mine}",
            (since, until, *([workspace] if workspace else [])),
        )[0]
        own = 0.0 if workspace else self.gateway.runtime.endpoints.own_costs(since, until)
        usd = round(float(row["usd"]) + own, 6)
        return {"usd": usd, "requests": int(row["requests"]), "estimated_usd": round(float(row["estimated"]), 6)}

    def view(self, workspace: str = "") -> dict[str, Any]:
        """The cost view (plan s34's interface): today and this month against the limits, a pause and a warning, with
        their words; the currency, this computer's zone and the newest revision; and, asked for a workspace, its own
        today and this month (`workspace`; the limits stay the whole cloud's)."""
        periods = self.periods()
        found: dict[str, Any] = {}
        own: dict[str, Any] = {"name": workspace}
        for name, words in (("today", "today"), ("month", "this month")):
            for whose, into in (("", found), *([(workspace, own)] if workspace else [])):
                totals = self.totals(periods[name]["from"], periods[name]["until"], whose)
                said = ("≈ " if totals["estimated_usd"] else "") + f"{_money(totals['usd'])} {words}"
                into[name] = {**totals, **periods[name], "said": said}
        settings = self.gateway.cost_settings()
        limits = {"day_usd": settings.day_usd, "month_usd": settings.month_usd, "warn_at": settings.warn_at}
        offset = self._here().utcoffset()
        return {
            "today": found["today"],
            "month": found["month"],
            "limits": {**limits, "said": _limits_said(settings.day_usd, settings.month_usd)},
            "paused": self.paused_view(),
            "warned": self.warned_view(),
            "days": "local",
            "currency": "USD",
            "zone": _zone(offset),
            "revision": self.revision(),
            "said": f"cloud {_money(found['today']['usd'])} today · {_money(found['month']['usd'])} this month",
            "workspace": own if workspace else None,
        }

    def sessions(self, *, workspace: str = "", limit: int = 50, after: int = 0) -> list[dict[str, Any]]:
        """Each session's cost, its subagents' counted in, newest first; only those changed after a revision."""
        where, params = ["1 = 1"], []
        if workspace:
            where.append("workspace = ?")
            params.append(workspace)
        rows = self.kernel.store.read(
            "SELECT CASE WHEN parent != '' THEN parent ELSE session END AS root, MIN(workspace) AS workspace,"
            " SUM(usd) AS usd, SUM(CASE WHEN code = '' THEN 1 ELSE 0 END) AS requests,"
            " SUM(CASE WHEN how = 'estimate' THEN usd ELSE 0 END) AS estimated, MIN(time) AS first, MAX(time) AS last,"
            f" MAX(rev) AS rev FROM cloud_costs WHERE {' AND '.join(where)} AND session != ''"
            " GROUP BY root HAVING MAX(rev) > ? ORDER BY last DESC LIMIT ?",
            (*params, after, limit),
        )
        return [
            {
                "session": row["root"], "workspace": row["workspace"], "usd": round(float(row["usd"]), 6),
                "requests": int(row["requests"]), "estimated_usd": round(float(row["estimated"]), 6),
                "first": row["first"], "last": row["last"], "rev": int(row["rev"]),
                "said": _counted(float(row["usd"]), int(row["requests"]), float(row["estimated"])),
            }
            for row in rows
        ]  # fmt: skip

    def for_sessions(self, boxes: dict[str, list[str]]) -> dict[str, Any] | None:
        """What a flow's boxes cost, each by its sessions (their subagents' too), and their total; None when none of
        them used the cloud."""
        shown: dict[str, dict[str, Any]] = {}
        usd = estimated = 0.0
        requests = 0
        for box, sessions in boxes.items():
            if not sessions:
                continue
            marks = ", ".join("?" for _ in sessions)
            row = self.kernel.store.read(
                "SELECT COALESCE(SUM(usd), 0) AS usd, COALESCE(SUM(CASE WHEN code = '' THEN 1 ELSE 0 END), 0) AS"
                " requests, COALESCE(SUM(CASE WHEN how = 'estimate' THEN usd ELSE 0 END), 0) AS estimated FROM"
                f" cloud_costs WHERE session IN ({marks}) OR parent IN ({marks})",
                (*sessions, *sessions),
            )[0]
            if not row["requests"] and not row["usd"]:
                continue
            box_usd, box_requests = round(float(row["usd"]), 6), int(row["requests"])
            shown[box] = {"usd": box_usd, "requests": box_requests,
                          "said": _counted(box_usd, box_requests, float(row["estimated"]))}  # fmt: skip
            usd += box_usd
            requests += box_requests
            estimated += float(row["estimated"])
        if not shown:
            return None
        return {"usd": round(usd, 6), "estimated_usd": round(estimated, 6), "requests": requests, "boxes": shown,
                "said": _counted(usd, requests, estimated)}  # fmt: skip

    def announce(self) -> None:
        """`gateway.cost`, the totals, when they changed: at most every five seconds."""
        periods = self.periods()
        today = self.totals(periods["today"]["from"], periods["today"]["until"])
        month = self.totals(periods["month"]["from"], periods["month"]["until"])
        totals = (today["usd"], month["usd"], month["estimated_usd"])
        moment = time.monotonic()
        if totals == self._told or moment - self._told_at < COST_SECONDS:
            return
        self._told, self._told_at = totals, moment
        self.kernel.events.record(
            "gateway.cost",
            summary=f"cloud {_money(today['usd'])} today · {_money(month['usd'])} this month",
            actor=GATEWAY,
            data={"today_usd": today["usd"], "month_usd": month["usd"], "estimated_usd": month["estimated_usd"]},
        )

    # The limits (design 0016 §11, decision 0104): told once at 80%, the cloud paused at a limit, the owner asked.

    def check_limits(self, who: str = "") -> None:
        """Look at the spending against the limits: tell the owner once at `warn_at` of a limit; at a limit, pause the
        cloud (the routes say it, and the gateway holds each new cloud request) and ask once whether to raise it; once
        the limit is raised (`who` raised it) or its period ended, let the cloud go on."""
        settings = self.gateway.cost_settings()
        periods = self.periods()
        reached = None
        for by, limit, period in (("day", settings.day_usd, periods["today"]), ("month", settings.month_usd,
                                                                                  periods["month"])):  # fmt: skip
            if limit is None:
                continue
            spent = self.totals(period["from"], period["until"])["usd"]
            if spent >= limit:
                reached = {"by": by, "spent_usd": spent, "limit_usd": limit, "period": period}
                break
            if spent >= settings.warn_at * limit and (by, period["local"]) not in self._warned:
                self._warned.add((by, period["local"]))
                self._warning = {"by": by, "spent_usd": spent, "limit_usd": limit, "local": period["local"]}
                self.kernel.events.record(
                    "gateway.limit_warned",
                    summary=_warned_words(by, spent, limit),
                    actor=GATEWAY,
                    data={"by": by, "spent_usd": spent, "limit_usd": limit},
                )
        if self._warning is not None and self._warning["local"] not in (periods["today"]["local"],
                                                                         periods["month"]["local"]):  # fmt: skip
            self._warning = None
        paused = self._paused
        if paused is not None:
            same = reached is not None and (reached["by"], reached["period"]["local"]) == (
                paused["by"],
                paused["local"],
            )
            if not same:
                self._release(paused, reached, who, periods)
            elif reached is not None and reached["limit_usd"] != paused["limit_usd"]:  # changed, and still reached
                self._ask_again(paused)
        if reached is not None and self._paused is None:
            self._pause(reached)

    def _pause(self, reached: dict[str, Any]) -> None:
        by, spent, limit, period = reached["by"], reached["spent_usd"], reached["limit_usd"], reached["period"]
        whose = "today's" if by == "day" else "this month's"
        until = "until the day ends" if by == "day" else "until the month ends"
        draft = QuestionDraft(
            type="choice",
            title=f"Cloud spending reached {whose} limit of {_money(limit)} ({_money(spent)} spent): raise it?",
            detail=(
                f"Each new cloud request is held before it is sent {until}, or until you raise the limit; requests "
                f"already in flight finish, so what was spent can pass the limit by what they cost "
                f"({_money(max(spent - limit, 0.0))} so far)."
            ),
            options=[
                Option(id="double", label=f"Raise {whose} limit to {_money(limit * 2)}", key="y",
                       effect=f"{whose} limit becomes {_money(limit * 2)}; the held requests go on"),
                Option(id="raise", label="Raise it to …", key="r", effect="raise it to the amount you give",
                       asks=Asked(kind="number", unit="USD", min=_above(spent), max=RAISE_MOST, step=0.01)),
                Option(id="keep", label="Keep the cloud paused", key="n", effect=f"the cloud stays paused {until}"),
            ],
            default="keep",
            expires=from_text(period["until"]),
            urgency="high",
            about=Subject(kind="cost", id=f"{by}:{period['local']}"),
        )  # fmt: skip
        question = self.kernel.questions.ask(draft, asked_by=GATEWAY)
        self._paused = {
            "by": by, "since": to_text(self.kernel.clock.now()), "spent_usd": spent, "limit_usd": limit,
            "question": question.id, "local": period["local"],
        }  # fmt: skip
        self.kernel.events.record(
            "gateway.limit_reached",
            summary=_paused_words(by, spent, limit),
            actor=GATEWAY,
            data={"by": by, "spent_usd": spent, "limit_usd": limit, "question": question.id},
        )

    def _ask_again(self, paused: dict[str, Any]) -> None:
        """The limit was changed and the spending is still at it: its question, answered or not, is asked again with
        the new numbers, so the cloud never stays paused with nothing to answer."""
        self._paused = None
        with suppress(QuestionError):
            if self.kernel.questions.get(str(paused["question"])).status == "waiting":
                self.kernel.questions.withdraw(str(paused["question"]), reason="the limit changed", by=GATEWAY)

    def _release(
        self, paused: dict[str, Any], reached: dict[str, Any] | None, who: str, periods: dict[str, dict[str, Any]]
    ) -> None:
        self._paused = None
        by = str(paused["by"])
        ended = paused["local"] != periods["today" if by == "day" else "month"]["local"]
        with suppress(QuestionError):
            if self.kernel.questions.get(str(paused["question"])).status == "waiting":
                self.kernel.questions.withdraw(str(paused["question"]), reason="the cloud goes on", by=GATEWAY)
        settings = self.gateway.cost_settings()
        limit = settings.day_usd if by == "day" else settings.month_usd
        said = ("the day ended" if by == "day" else "the month ended") if ended else (who or "you")
        self.kernel.events.record(
            "gateway.limit_raised",
            summary=f"the cloud goes on: {said}" + (f" ({'today' if by == 'day' else 'this month'}: {_money(limit)})"
                                                    if limit is not None else ""),
            actor=GATEWAY,
            data={"by": by, "limit_usd": limit, "who": said},
        )  # fmt: skip

    def _resolved(self, question: Question) -> None:
        """The limit question answered: *double* or *raise* writes the new limit, recorded with who answered; *keep*
        (or no answer) leaves the cloud paused until the period ends."""
        if question.about is None or question.about.kind != "cost" or question.status != "answered":
            return
        if question.answer is None or question.answer.option not in ("double", "raise"):
            return
        by = question.about.id.split(":", 1)[0]
        field = "day_usd" if by == "day" else "month_usd"
        current = getattr(self.gateway.cost_settings(), field) or 0.0
        amount = current * 2 if question.answer.option == "double" else float(
            question.answer.text.strip().lstrip("$").replace(",", "")
        )  # fmt: skip
        self.gateway.set_limits({field: round(amount, 2)}, actor=question.answer.by)

    def paused_view(self) -> dict[str, Any] | None:
        """The cloud's pause at a limit, with its words; None while it is not paused."""
        if self._paused is None:
            return None
        found = {key: self._paused[key] for key in ("by", "since", "spent_usd", "limit_usd", "question")}
        said = _paused_words(str(found["by"]), float(found["spent_usd"]), float(found["limit_usd"]))
        return {**found, "held": self.held, "said": said}

    def warned_view(self) -> dict[str, Any] | None:
        """A limit nearly reached, with its words; None while none is (or the cloud is paused)."""
        if self._warning is None or self._paused is not None:
            return None
        found = {key: self._warning[key] for key in ("by", "spent_usd", "limit_usd")}
        return {**found, "said": _warned_words(str(found["by"]), float(found["spent_usd"]), float(found["limit_usd"]))}

    def routes(self) -> dict[str, Any]:
        """What the routes the gateway follows carry of the spending (design 0016 §12): today's and this month's, the
        limits, and the last entry taken of the spool's run, so the gateway counts those it has not given yet."""
        periods = self.periods()
        settings = self.gateway.cost_settings()
        return {
            "day_usd": self.totals(periods["today"]["from"], periods["today"]["until"])["usd"],
            "month_usd": self.totals(periods["month"]["from"], periods["month"]["until"])["usd"],
            "taken": self._last(self._run) if self._run else 0,
            "run": self._run,
            "limit_day_usd": settings.day_usd,
            "limit_month_usd": settings.month_usd,
        }


HOW = {  # how a request's cost is known, in words (design 0016 §12)
    "usage": "OpenRouter's own figure, from the answer",
    "generation": "OpenRouter's own figure, asked after the answer was cut short",
    "estimate": "an estimate from its tokens and the model's prices, until OpenRouter's figure comes",
}


def _how(value: object) -> str:
    return str(value) if value in ("usage", "generation", "estimate") else "usage"


def _request(row: Any) -> dict[str, Any]:
    """A cost row as clients read it (plan s34's interface), with its revision and its words."""
    usd, how = float(row["usd"]), str(row["how"])
    said = ("≈ " if how == "estimate" else "") + _money(usd)
    return {
        "id": row["request"], "time": row["time"], "session": row["session"], "workspace": row["workspace"],
        "preset": row["preset"], "model": row["model"], "tokens": json.loads(row["tokens"] or "{}"), "usd": usd,
        "how": how, "status": row["status"], "code": row["code"], "rev": int(row["rev"]), "said": said,
        "how_said": HOW.get(how, how),
    }  # fmt: skip


def _money(usd: float) -> str:
    """US dollars as people read an amount, small ones too: $1.29, $0.0123, $0.000021."""
    if usd >= 0.01 or usd == 0:
        return f"${usd:.2f}"
    return "$" + f"{usd:.6f}".rstrip("0").rstrip(".")


def _counted(usd: float, requests: int, estimated: float) -> str:
    """An amount and its requests, as people read them: "$0.84 · 142 requests", "≈ $0.03 · 1 request"."""
    noun = "request" if requests == 1 else "requests"
    return ("≈ " if estimated else "") + f"{_money(usd)} · {requests} {noun}"


def _limits_said(day: float | None, month: float | None) -> str:
    """The limits in words: "today's limit $5.00; no monthly limit"."""
    if day is None and month is None:
        return "no daily or monthly limit"
    said = [f"today's limit {_money(day)}" if day is not None else "no daily limit"]
    said.append(f"this month's limit {_money(month)}" if month is not None else "no monthly limit")
    return "; ".join(said)


def _zone(offset: timedelta | None) -> str:
    """A zone's offset as people read it: "UTC-04:00"."""
    minutes = int((offset or timedelta()).total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _warned_words(by: str, spent: float, limit: float) -> str:
    """A limit nearly reached, in words: "cloud: $4.02 of today's $5.00"."""
    return f"cloud: {_money(spent)} of {'today' if by == 'day' else 'this month'}'s {_money(limit)}"


def _above(spent: float) -> float:
    """The least limit, in whole cents, above what was spent: a raise to it lets the cloud go on."""
    return round(math.floor(spent * 100 + 1e-6) / 100 + 0.01, 2)


def _paused_words(by: str, spent: float, limit: float) -> str:
    """The cloud paused, in words: "cloud paused: today's limit of $5.00 reached ($5.02 spent)"."""
    whose = "today's" if by == "day" else "this month's"
    return f"cloud paused: {whose} limit of {_money(limit)} reached ({_money(spent)} spent)"
