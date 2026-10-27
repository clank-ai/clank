"""The phone's way in, checked from this PC (design 0025 §2, when the page does not load): what can be seen from here
when a phone cannot open the phone page, each finding in words with what to do, in the doctor's shape (`id`, `title`,
`status`: passed, warning, failed or skipped, `detail`, `fix`).

What it reads (`Facts`): Tailscale's status (the owner's phones on the tailnet, online or offline, when last seen,
their sign-in; MagicDNS; the certificates), what Tailscale serves (where the tailnet port goes; Funnel), the listener's
state, the listener's log (which device reached it today, when, and why it was refused: the log keeps where each request
came from, as Tailscale's proxy says it), the pairing code waiting, what this PC got when it opened its own published
address, and, while Funnel is on for this machine, what one public DNS server says for the PC's name (`probes.py`).
Funnel gives the name public addresses, Tailscale's relays, which do not carry the phone page's port: a phone that does
not ask Tailscale's DNS for the name (iCloud Private Relay does so for Safari) waits, then cannot connect, and nothing
reaches the PC (the owner's first scan, 2026-10-26). The checks come in the order a failed scan is understood: the
phones, what reached the listener, Funnel, then this PC's side. Nothing here changes anything.

The service checks while remote access is on (`Remote.checkup`: the console's Phone page, `clank remote status`);
`doctor` checks from the files alone for `clank doctor`, which runs without the service.
"""

import socket
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from clank.components.remote import probes, tailnet
from clank.components.remote.kinds import RemoteSettings
from clank.components.remote.probes import Public, Reached
from clank.components.remote.traffic import KEPT, Traffic
from clank.kernel.access import read_connection
from clank.kernel.clock import from_text
from clank.kernel.home import Home
from clank.kernel.settings import read_record

HINT = "Page won't load? On the iPhone: Tailscale on, iCloud Private Relay off."  # under the QR (console, CLI)
PHONE_SYSTEMS = ("ios", "android")
SOON_DAYS = 3  # a phone's Tailscale sign-in that expires within this many days is said
REFUSED = (401, 403)
LOOPBACK = ("127.0.0.1", "::1")
AGENTS = (("iPhone", "an iPhone"), ("iPad", "an iPad"), ("Android", "an Android phone"))
ADMIN_DNS = "Tailscale's admin console, DNS page (https://login.tailscale.com/admin/dns)"
TOGGLE = (
    "turn remote access off and on again: x twice on the console's Phone page (or `clank remote off`, then "
    "`clank remote on`)"
)
SIGN_IN = "open Tailscale on this PC and sign in (or run `tailscale up`)"
NEW_QR = "make a new QR (p on the console's Phone page, or `clank remote pair`) and scan it"
NOT_REACHED = (
    "if you tried from the phone, its requests never reached this PC: the Tailscale app on it must say Connected, "
    "with Use Tailscale DNS settings on"
)
PRIVATE_RELAY = (
    "on the iPhone, turn off iCloud Private Relay (Settings, your name, iCloud, Private Relay), then turn Airplane "
    "Mode on and off to clear its DNS cache; or, if nothing on this PC needs Funnel, turn it off (`tailscale funnel "
    "status` shows what it publishes)"
)
SELF_FIX = (
    "if this PC cannot open it, no phone can: the checks above say what is wrong; then turn remote access off and on "
    "again (x twice on the console's Phone page)"
)


@dataclass(frozen=True)
class Facts:
    """What the checkup reads: the settings; Tailscale's status ({} when it did not answer, and why: `problem`) and
    what it serves; the listener's state as (status, detail, fix), its detail said for it when empty; what this PC got
    from its own address and what public DNS said (None: not asked); the listener's log, newest first; the pairing code
    waiting (its `made`); now, and the zone whose day is today (None: this computer's)."""

    settings: RemoteSettings
    status: dict[str, Any]
    now: datetime
    problem: str = ""
    serve: dict[str, Any] = field(default_factory=dict)
    listener: tuple[str, str, str] = ("passed", "", "")
    reached: Reached | None = None
    public: Public | None = None
    exchanges: Sequence[dict[str, Any]] = ()
    pairing: dict[str, Any] | None = None
    zone: tzinfo | None = None


@dataclass(frozen=True)
class Phone:
    """A phone (or tablet) on the tailnet, as Tailscale says it: its name there, its system, online or not, when last
    seen, when its sign-in expires and whether it has, its user's id, its addresses."""

    name: str
    system: str
    online: bool
    seen: datetime | None
    expires: datetime | None
    expired: bool
    user: str
    addresses: tuple[str, ...]

    @property
    def kind(self) -> str:
        """What the owner calls it: iPhone, iPad or phone."""
        if "ipad" in self.name.lower():
            return "iPad"
        return "iPhone" if self.system.lower() == "ios" else "phone"


def phones(status: dict[str, Any]) -> list[Phone]:
    """The phones and tablets on the tailnet (iOS, Android), the online ones first, then the most recently seen."""
    found = []
    for peer in (status.get("Peer") or {}).values():
        if not isinstance(peer, dict) or str(peer.get("OS") or "").lower() not in PHONE_SYSTEMS:
            continue
        found.append(
            Phone(
                _name(peer), str(peer.get("OS")), bool(peer.get("Online")), _when(peer.get("LastSeen")),
                _when(peer.get("KeyExpiry")), bool(peer.get("Expired")), str(peer.get("UserID", "")),
                tuple(str(address) for address in peer.get("TailscaleIPs") or ()),
            )
        )  # fmt: skip
    return sorted(found, key=lambda phone: (not phone.online, -(phone.seen.timestamp() if phone.seen else 0.0)))


def funnel_ports(serve: dict[str, Any], host: str) -> list[int]:
    """The ports of this machine Tailscale Funnel publishes to the internet, from what it serves."""
    found = set()
    for key, on in (serve.get("AllowFunnel") or {}).items():
        name, _, port = str(key).rpartition(":")
        if on and port.isdigit() and (not host or name == host):
            found.add(int(port))
    return sorted(found)


def checks(facts: Facts) -> list[dict[str, str]]:
    """Every check, in the order the owner reads them; those that need Tailscale only when it runs here."""
    status = facts.status
    running = status.get("BackendState") == "Running"
    me = status.get("Self") or {}
    host = str(me.get("DNSName") or "").rstrip(".")
    users = status.get("User") or {}
    owner = _login(users, str(me.get("UserID", "")))
    funnel = funnel_ports(facts.serve, host) if running else []
    found = _phones(facts, owner, users) if running else []
    found += _heard(facts, owner, bool(funnel))
    if running:
        found.append(_funnel(facts, host, funnel, me))
    found += [_tailscale(facts, owner, host, me), _listener(facts)]
    if running:
        found += [_published(facts, host), _magicdns(status, host), _https(status, host)]
        if facts.reached is not None:
            found.append(_self(facts.reached, f"https://{host}:{facts.settings.tailnet_port}/"))
    return found


def doctor(home: Home) -> list[dict[str, Any]]:
    """The checkup for `clank doctor`, from the files alone (it runs without the service): nothing while remote access
    is off; each check's id and title marked as the phone's. This PC opens its own address only while the listener
    answers."""
    settings = _settings(home)
    if isinstance(settings, str):
        return [_check("remote.settings", "Phone: config/remote.json", "failed", settings, "correct the file")]
    if not settings.on:
        return []
    status, problem = tailnet.status()
    running = status.get("BackendState") == "Running"
    serve = tailnet.serve_config() if running else {}
    host = str((status.get("Self") or {}).get("DNSName") or "").rstrip(".")
    listener = _listening(home, settings.port)
    reached = None
    if running and host and listener[0] == "passed":
        reached = probes.reach(f"https://{host}:{settings.tailnet_port}/")
    public = probes.public_addresses(host) if running and host and funnel_ports(serve, host) else None
    exchanges = Traffic(home.logs / "phone").recent(limit=KEPT)
    facts = Facts(settings, status, datetime.now(UTC), problem, serve, listener, reached, public, exchanges)
    return [{**check, "id": f"remote.{check['id']}", "title": f"Phone: {check['title']}"} for check in checks(facts)]


def _check(id: str, title: str, status: str, detail: str, fix: str = "") -> dict[str, str]:
    return {"id": id, "title": title, "status": status, "detail": detail, "fix": fix}


def _phones(facts: Facts, owner: str, users: dict[str, Any]) -> list[dict[str, str]]:
    """Each of the owner's phones; when none is on the tailnet, that, with the others' phones and their accounts."""
    me = str((facts.status.get("Self") or {}).get("UserID", ""))
    every = phones(facts.status)
    mine = [phone for phone in every if phone.user == me]
    if mine:
        return [_phone(phone, facts.now) for phone in mine]
    others = [f"{phone.name} is, signed in as {_login(users, phone.user) or 'another account'}" for phone in every]
    detail = "none of yours is on your tailnet" + (f" ({'; '.join(others)})" if others else "")
    fix = f"install Tailscale on the iPhone (App Store) and sign in as {owner}, the account this PC uses"
    return [_check("phone", "A phone on the tailnet", "warning", detail, fix)]


def _phone(phone: Phone, now: datetime) -> dict[str, str]:
    id, title, app = f"phone:{phone.name}", phone.name, f"open the Tailscale app on the {phone.kind}"
    if phone.expired:
        return _check(id, title, "failed", "its Tailscale sign-in expired", f"{app} and sign in again")
    if not phone.online:
        seen = f" (last seen {_ago((now - phone.seen).total_seconds())})" if phone.seen else ""
        fix = f"{app} and switch it on (it says Connected), then scan the QR again"
        return _check(id, title, "warning", f"offline on your tailnet{seen}", fix)
    if phone.expires is not None and phone.expires - now < timedelta(days=SOON_DAYS):
        detail = (
            f"online on your tailnet; its Tailscale sign-in expires in {_left((phone.expires - now).total_seconds())}"
        )
        fix = f"{app} and sign in again before then (or turn off key expiry for it in Tailscale's admin console)"
        return _check(id, title, "warning", detail, fix)
    return _check(id, title, "passed", "online on your tailnet")


def _heard(facts: Facts, owner: str, funnel: bool) -> list[dict[str, str]]:
    """Which device reached the listener last today, and the last refusal when it is not that one."""
    names, own = _names(facts.status), _own(facts.status)
    devices = [each for each in facts.exchanges if _from_a_device(each, own) and _time(each) is not None]
    start = _midnight(facts.now, facts.zone)
    today = [each for each in devices if (_time(each) or start) >= start]
    fix = NOT_REACHED + (", and iCloud Private Relay off (see Funnel)" if funnel else "")
    made = _when(facts.pairing.get("made")) if facts.pairing else None
    if made is not None and not any((_time(each) or made) > made for each in devices):
        detail = f"no phone has reached Clank since the QR was made at {_clock(made, facts.zone)}"
        return [_check("heard", "Reached Clank", "warning", detail, fix)]
    if not today:
        return [_check("heard", "Reached Clank", "warning", "no phone has reached Clank today", fix)]
    last = today[0]
    if last["status"] in REFUSED:
        heard = _check("heard", "Reached Clank", "warning", _said(last, names, facts.zone, refused=True),
                       _refusal_fix(last, owner))  # fmt: skip
    else:
        heard = _check("heard", "Reached Clank", "passed", _said(last, names, facts.zone))
    refusals = [each for each in today if each["status"] in REFUSED]
    if not refusals or refusals[0] is last:
        return [heard]
    refusal = refusals[0]
    later = today[: today.index(refusal)]
    served = any(_source(each) == _source(refusal) and each["status"] < 400 for each in later)
    detail = _said(refusal, names, facts.zone) + ("; served since" if served else "")
    fix = "" if served else _refusal_fix(refusal, owner)
    return [heard, _check("refused", "Last refusal", "passed" if served else "warning", detail, fix)]


def _said(exchange: dict[str, Any], names: dict[str, str], zone: tzinfo | None, refused: bool = False) -> str:
    """An exchange in words: who, when, what it asked, and why it was refused."""
    when = _clock(_time(exchange) or datetime.now(UTC), zone)
    asked = f"{exchange.get('method', 'GET')} {exchange.get('path', '/')}"
    why = str((exchange.get("refused") or {}).get("why") or "")
    because = f": {why}" if why else ""
    if refused:
        return f"{_who(exchange, names)} at {when}, refused ({asked}){because}"
    return f"{_who(exchange, names)} at {when} ({asked}){because}"


def _refusal_fix(exchange: dict[str, Any], owner: str) -> str:
    """What to do about a refusal, by its kind (`app.py` names it)."""
    login = str((exchange.get("origin") or {}).get("login") or "another account")
    return {
        "code": f"the QR's code was spent or had expired: {NEW_QR}",
        "tries": f"too many wrong codes: wait fifteen minutes, then {NEW_QR}",
        "account": f"the phone's Tailscale is signed in as {login}: sign in as {owner} in the Tailscale app on it, "
        "then scan the QR again",
        "login": f"Tailscale did not say who asked: sign in to the Tailscale app on the phone as {owner}",
        "owner": "this PC's Tailscale did not say its own account: check that Tailscale runs and is signed in here",
        "funnel": "it came through Funnel, from the internet: turn Tailscale on on the phone, then open the link",
        "paired": f"pair it: {NEW_QR}",
        "tailscale": "open it through Tailscale: the QR's link, with Tailscale on on the phone",
    }.get(str((exchange.get("refused") or {}).get("kind") or ""), "")


def _funnel(facts: Facts, host: str, ports: list[int], me: dict[str, Any]) -> dict[str, str]:
    """Whether Funnel gives this PC's name a public address, what public DNS says for it, and how a phone gets past."""
    if not ports:
        return _check("funnel", "Funnel", "passed", f"off on this PC: {host} resolves only through your tailnet")
    port = facts.settings.tailnet_port
    said = f"on for port{'s' if len(ports) > 1 else ''} {_words([str(each) for each in ports])}: {host} also resolves "
    said += "on the internet"
    public = facts.public
    if public is not None:
        server = public.server + (", Cloudflare's public DNS" if public.server == probes.PUBLIC_DNS else "")
        ours = next((str(each) for each in me.get("TailscaleIPs") or () if ":" not in str(each)), "")
        if public.addresses:
            said += (
                f", to {_words(list(public.addresses))} (asked of {server}), not to {ours}, its address on your tailnet"
            )
        elif public.problem:
            said += f" ({public.server} could not be asked: {public.problem})"
        else:
            said += f" (though {public.server}, asked just now, gave no address for it)"
    said += ". A phone that does not ask Tailscale's DNS for it (iCloud Private Relay, or an answer kept from before "
    if port in ports:
        said += "Tailscale was on) reaches Tailscale's relay, and the listener refuses what comes from the internet"
    else:
        said += (
            f"Tailscale was on) reaches Tailscale's relay, which does not carry port {port}: Safari loads for a while, "
            "then cannot connect to the server"
        )
    return _check("funnel", "Funnel", "warning", said, PRIVATE_RELAY)


def _tailscale(facts: Facts, owner: str, host: str, me: dict[str, Any]) -> dict[str, str]:
    title = "Tailscale on this PC"
    if not facts.status:
        problem = facts.problem or "Tailscale did not answer"
        fix = (
            "install Tailscale (https://tailscale.com/download) and sign in" if "not installed" in problem else SIGN_IN
        )
        return _check("tailscale", title, "failed", problem, fix)
    state = facts.status.get("BackendState")
    if state != "Running":
        return _check("tailscale", title, "failed", f"Tailscale is {state or 'not running'} on this PC", SIGN_IN)
    ours = next((str(each) for each in me.get("TailscaleIPs") or () if ":" not in str(each)), "")
    return _check(
        "tailscale", title, "passed", f"signed in as {owner}; this PC is {host}" + (f" ({ours})" if ours else "")
    )


def _listener(facts: Facts) -> dict[str, str]:
    status, detail, fix = facts.listener
    return _check("listener", "The listener", status, detail or f"listens on this PC (127.0.0.1:{facts.settings.port})",
                  fix)  # fmt: skip


def _published(facts: Facts, host: str) -> dict[str, str]:
    """Where Tailscale sends the tailnet port: to the listener, on the tailnet only."""
    port, tailnet_port, title = facts.settings.port, facts.settings.tailnet_port, "Published"
    if (facts.serve.get("AllowFunnel") or {}).get(f"{host}:{tailnet_port}"):
        detail = f"Funnel is on for port {tailnet_port}: the phone page would face the internet"
        fix = f"turn Funnel off for it (`tailscale funnel --https={tailnet_port} off`): Clank publishes on the tailnet"
        return _check("published", title, "failed", detail, fix)
    handlers = ((facts.serve.get("Web") or {}).get(f"{host}:{tailnet_port}") or {}).get("Handlers") or {}
    proxy = str((handlers.get("/") or {}).get("Proxy") or "")
    if not proxy:
        return _check("published", title, "failed", f"Tailscale publishes nothing on port {tailnet_port}", TOGGLE)
    if proxy.rstrip("/") != f"http://127.0.0.1:{port}":
        detail = f"port {tailnet_port} goes to {proxy}, not to the listener (127.0.0.1:{port})"
        return _check("published", title, "failed", detail, TOGGLE)
    detail = f"https://{host}:{tailnet_port}/ goes to the listener (127.0.0.1:{port}), on your tailnet only"
    return _check("published", title, "passed", detail)


def _magicdns(status: dict[str, Any], host: str) -> dict[str, str]:
    enabled = (status.get("CurrentTailnet") or {}).get("MagicDNSEnabled")
    if enabled is None:
        return _check("magicdns", "MagicDNS", "skipped", "Tailscale did not say")
    if enabled:
        return _check("magicdns", "MagicDNS", "passed", f"on: your devices find {host} by its name")
    detail = f"off in your tailnet: a phone cannot find {host} by its name"
    return _check("magicdns", "MagicDNS", "failed", detail, f"turn MagicDNS on in {ADMIN_DNS}")


def _https(status: dict[str, Any], host: str) -> dict[str, str]:
    if host in (status.get("CertDomains") or ()):
        return _check("https", "HTTPS certificates", "passed", f"on: {host} has a certificate")
    detail = "off in your tailnet: the phone page cannot be served over HTTPS"
    fix = f"turn HTTPS Certificates on in {ADMIN_DNS}, then turn remote access off and on"
    return _check("https", "HTTPS certificates", "failed", detail, fix)


def _self(reached: Reached, url: str) -> dict[str, str]:
    if reached.status is None:
        return _check("self", "This PC reaches it", "failed", f"{url} did not answer: {reached.said}", SELF_FIX)
    if reached.status < 400:
        return _check("self", "This PC reaches it", "passed", f"{url} answered in {round(reached.ms):,} ms")
    detail = f"{url} answered {reached.status}" + (f": {reached.said}" if reached.said else "")
    return _check("self", "This PC reaches it", "failed", detail, SELF_FIX)


def _listening(home: Home, port: int) -> tuple[str, str, str]:
    """Whether the listener answers, seen from outside the service: the service runs, its port takes a connection."""
    if read_connection(home) is None:
        return (
            "failed",
            "Clank's service does not run: nothing listens for the phone",
            "start it: `clank serve --background`",
        )
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    except OSError:
        return "failed", f"nothing listens on 127.0.0.1:{port}", f"the console's Phone page (F9) says why; {TOGGLE}"
    return "passed", "", ""


def _settings(home: Home) -> RemoteSettings | str:
    path = home.config / f"{RemoteSettings.KIND}.json"
    if not path.is_file():
        return RemoteSettings()
    found = read_record(RemoteSettings, path)
    if isinstance(found, list):
        return "; ".join(str(problem) for problem in found)
    return RemoteSettings.model_validate(found[0].model_dump())


def _name(peer: dict[str, Any]) -> str:
    """A peer's name on the tailnet: its DNS name's first label (iOS calls itself `localhost`), else its host name."""
    dns = str(peer.get("DNSName") or "").rstrip(".")
    return dns.split(".")[0] if dns else str(peer.get("HostName") or "a device")


def _names(status: dict[str, Any]) -> dict[str, str]:
    """Each tailnet address of a peer, with the peer's name."""
    return {
        str(address): _name(peer)
        for peer in (status.get("Peer") or {}).values()
        if isinstance(peer, dict)
        for address in peer.get("TailscaleIPs") or ()
    }


def _own(status: dict[str, Any]) -> set[str]:
    """This PC's own addresses: its tailnet's and the loopback's."""
    return {*LOOPBACK, *(str(address) for address in (status.get("Self") or {}).get("TailscaleIPs") or ())}


def _from_a_device(exchange: dict[str, Any], own: set[str]) -> bool:
    """Whether an exchange came from a device, not from this PC (its own checkup, a local client); a line written before
    the log kept where requests came from counts when it names a paired device."""
    origin = exchange.get("origin")
    if not isinstance(origin, dict):
        return bool(exchange.get("device_name"))
    address = str(origin.get("address") or "")
    return origin.get("agent") != probes.AGENT and bool(address) and address not in own


def _who(exchange: dict[str, Any], names: dict[str, str]) -> str:
    """The device an exchange came from: its name on the tailnet, else its pairing's name or its browser's kind."""
    origin = exchange.get("origin") or {}
    address = str(origin.get("address") or "")
    if address in names:
        return names[address]
    agent = str(origin.get("agent") or "")
    kind = next((said for marker, said in AGENTS if marker in agent), "")
    base = str(exchange.get("device_name") or "") or kind or "a device"
    return f"{base} ({address})" if address else base


def _source(exchange: dict[str, Any]) -> str:
    return str((exchange.get("origin") or {}).get("address") or exchange.get("device") or "")


def _login(users: dict[str, Any], user: str) -> str:
    return str((users.get(user) or {}).get("LoginName") or "").lower()


def _time(exchange: dict[str, Any]) -> datetime | None:
    try:
        return from_text(str(exchange["time"]))
    except (KeyError, ValueError):
        return None


def _when(text: Any) -> datetime | None:
    """A time Tailscale wrote, or None (none written, or its zero time, the year 1)."""
    if not isinstance(text, str) or not text or text.startswith("0001-"):
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _midnight(now: datetime, zone: tzinfo | None) -> datetime:
    local = now.astimezone(zone) if zone else now.astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _clock(moment: datetime, zone: tzinfo | None) -> str:
    return (moment.astimezone(zone) if zone else moment.astimezone()).strftime("%H:%M")


def _ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago"


def _left(seconds: float) -> str:
    hours = int(seconds // 3600)
    if hours < 24:
        return f"{max(hours, 1)} h"
    days = hours // 24
    return f"{days} day" if days == 1 else f"{days} days"


def _words(items: Sequence[str]) -> str:
    """Items as a sentence lists them: a, b and c."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
