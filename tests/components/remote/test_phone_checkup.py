"""Design 0025 §2 (when the page does not load): the phone's way in, checked from this PC, each finding in words with
what to do. The owner's phones on the tailnet, online or offline and when last seen, a sign-in expired or about to; a
phone of another account; which device reached the listener today, when, and why it was refused; Funnel on for this
PC, which gives its name a public address that leads a phone not asking Tailscale's DNS to Tailscale's relay; Tailscale
on this PC, the listener, where the tailnet port goes, MagicDNS and HTTPS certificates; and this PC opening its own
published address. When Tailscale cannot say, only what does not need it is checked."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from clank.components.remote.checkup import Facts, checks
from clank.components.remote.kinds import RemoteSettings
from clank.components.remote.probes import Public, Reached
from tests.fakes.tailscale import HOST, OTHER, OWNER, PC, PHONE, phone, served, status

NOW = datetime(2026, 10, 26, 20, 0, tzinfo=UTC)
IPHONE_SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Safari/604.1"
SPENT = {"kind": "code", "why": "that code does not pair: make a new one on the computer (Phone, F9, p)"}


def facts(**changes: Any) -> Facts:
    """The checkup's facts: remote access on, the owner's iPhone offline since 17:00, the listener published and
    answering this PC in 240 ms; `changes` replace any."""
    found = Facts(
        settings=RemoteSettings(on=True),
        status=status(phone()),
        now=NOW,
        serve=served(),
        reached=Reached(200, 240.0),
        zone=UTC,
    )
    return replace(found, **changes)


def checked(given: Facts) -> dict[str, dict[str, str]]:
    return {check["id"]: check for check in checks(given)}


def exchange(time: str, path: str, status: int, address: str = PHONE, **more: Any) -> dict[str, Any]:
    """A line of the listener's log, as `Traffic.recent` gives it: from the phone's tailnet address unless named."""
    return {
        "id": f"x-{time[11:19]}", "time": time, "device": "", "device_name": "", "method": "GET", "path": path,
        "query": "", "status": status, "origin": {"address": address, "login": OWNER, "agent": IPHONE_SAFARI}, **more,
    }  # fmt: skip


def test_an_offline_phone_is_said_with_when_it_was_last_seen_and_how_to_bring_it_back() -> None:
    found = checked(facts())["phone:my-iphone"]
    assert (found["title"], found["status"]) == ("my-iphone", "warning")
    assert found["detail"] == "offline on your tailnet (last seen 3 h ago)"
    assert found["fix"] == (
        "open the Tailscale app on the iPhone and switch it on (it says Connected), then scan the QR again"
    )


def test_an_online_phone_a_sign_in_expired_or_about_to_and_another_accounts_phone_are_each_said() -> None:
    online = checked(facts(status=status(phone(Online=True))))["phone:my-iphone"]
    assert (online["status"], online["detail"], online["fix"]) == ("passed", "online on your tailnet", "")
    expired = checked(facts(status=status(phone(Expired=True))))["phone:my-iphone"]
    assert (expired["status"], expired["detail"]) == ("failed", "its Tailscale sign-in expired")
    assert expired["fix"] == "open the Tailscale app on the iPhone and sign in again"
    soon = checked(facts(status=status(phone(Online=True, KeyExpiry="2026-10-27T22:00:00Z"))))["phone:my-iphone"]
    assert (soon["status"], soon["detail"]) == (
        "warning",
        "online on your tailnet; its Tailscale sign-in expires in 1 day",
    )
    assert soon["fix"].startswith("open the Tailscale app on the iPhone and sign in again before then")
    android = phone(HostName="pixel", DNSName="pixel.tail0.ts.net.", OS="android", Online=True)
    assert checked(facts(status=status(android)))["phone:pixel"]["detail"] == "online on your tailnet"
    others = checked(facts(status=status(phone(UserID=2))))
    assert "phone:my-iphone" not in others, "only the owner's phones are listed"
    none = others["phone"]
    assert (none["title"], none["status"]) == ("A phone on the tailnet", "warning")
    assert none["detail"] == f"none of yours is on your tailnet (my-iphone is, signed in as {OTHER})"
    assert (
        none["fix"] == f"install Tailscale on the iPhone (App Store) and sign in as {OWNER}, the account this PC uses"
    )


def test_the_listeners_log_says_which_device_reached_clank_when_and_why_it_was_refused() -> None:
    log = [  # newest first
        exchange("2026-10-26T19:50:00.000Z", "/", 200, address=PC),  # this PC opening its own address: not a phone
        exchange("2026-10-26T18:02:00.000Z", "/pair", 403, refused=SPENT),
        exchange("2026-10-26T18:00:00.000Z", "/", 200),
    ]
    found = checked(facts(exchanges=log))
    heard = found["heard"]
    assert (heard["title"], heard["status"]) == ("Reached Clank", "warning")
    assert heard["detail"] == f"my-iphone at 18:02, refused (GET /pair): {SPENT['why']}"
    assert heard["fix"] == (
        "the QR's code was spent or had expired: make a new QR (p on the console's Phone page, or `clank remote pair`) "
        "and scan it"
    )
    assert "refused" not in found, "the last exchange is the refusal: said once"
    served_since = exchange("2026-10-26T18:05:00.000Z", "/api/stream", 200, device="dev-1", device_name="my phone")
    found = checked(facts(exchanges=[served_since, *log]))
    assert (found["heard"]["status"], found["heard"]["detail"]) == ("passed", "my-iphone at 18:05 (GET /api/stream)")
    refusal = found["refused"]
    assert (refusal["title"], refusal["status"], refusal["fix"]) == ("Last refusal", "passed", "")
    assert refusal["detail"] == f"my-iphone at 18:02 (GET /pair): {SPENT['why']}; served since"


def test_a_refusal_names_the_account_a_phone_came_with_and_a_device_tailscale_does_not_list_by_its_browser() -> None:
    account = {"kind": "account", "why": "this page answers only to this computer's own Tailscale user"}
    elsewhere = exchange("2026-10-26T19:10:00.000Z", "/pair", 403, address="100.64.0.9", refused=account)
    elsewhere["origin"]["login"] = OTHER
    heard = checked(facts(exchanges=[elsewhere]))["heard"]
    assert heard["detail"] == f"an iPhone (100.64.0.9) at 19:10, refused (GET /pair): {account['why']}"
    assert heard["fix"] == (
        f"the phone's Tailscale is signed in as {OTHER}: sign in as {OWNER} in the Tailscale app on it, then scan the "
        "QR again"
    )


def test_no_phone_reaching_clank_today_is_said_and_this_pcs_own_requests_and_unnamed_old_lines_do_not_count() -> None:
    log = [
        exchange("2026-10-26T19:50:00.000Z", "/", 200, address=PC),
        {"id": "x-old", "time": "2026-10-26T19:40:00.000Z", "device": "", "device_name": "", "method": "GET",
         "path": "/", "query": "", "status": 403},  # written before the log kept where a request came from
        exchange("2026-10-25T18:00:00.000Z", "/", 200),  # yesterday
    ]  # fmt: skip
    heard = checked(facts(exchanges=log))["heard"]
    assert (heard["status"], heard["detail"]) == ("warning", "no phone has reached Clank today")
    assert heard["fix"] == (
        "if you tried from the phone, its requests never reached this PC: the Tailscale app on it must say "
        "Connected, with Use Tailscale DNS settings on"
    )
    waiting = {"name": "my phone", "made": "2026-10-26T19:45:00.000Z", "expires": "2026-10-26T20:00:00.000Z"}
    heard = checked(facts(exchanges=log, pairing=waiting))["heard"]
    assert heard["detail"] == "no phone has reached Clank since the QR was made at 19:45"


def test_funnel_on_for_this_pc_is_said_with_its_public_address_and_how_a_phone_gets_past_it() -> None:
    public = Public(("203.0.113.5", "203.0.113.6"))
    found = checked(facts(status=status(phone(Online=True)), serve=served(funnel=(443,)), public=public))
    funnel = found["funnel"]
    assert (funnel["title"], funnel["status"]) == ("Funnel", "warning")
    assert funnel["detail"].startswith(
        f"on for port 443: {HOST} also resolves on the internet, to 203.0.113.5 and 203.0.113.6 (asked of 1.1.1.1, "
        f"Cloudflare's public DNS), not to {PC}, its address on your tailnet. "
    )
    assert "reaches Tailscale's relay, which does not carry port 8445" in funnel["detail"]
    assert funnel["fix"] == (
        "on the iPhone, turn off iCloud Private Relay (Settings, your name, iCloud, Private Relay), then turn Airplane "
        "Mode on and off to clear its DNS cache; or, if nothing on this PC needs Funnel, turn it off (`tailscale "
        "funnel status` shows what it publishes)"
    )
    assert found["heard"]["fix"].endswith(", and iCloud Private Relay off (see Funnel)")
    unasked = checked(facts(serve=served(funnel=(443, 8443)), public=Public((), "no answer within 2 s")))["funnel"]
    assert unasked["detail"].startswith(
        f"on for ports 443 and 8443: {HOST} also resolves on the internet (1.1.1.1 could not be asked: no answer "
        "within 2 s). "
    )
    off = checked(facts())["funnel"]
    assert (off["status"], off["detail"]) == ("passed", f"off on this PC: {HOST} resolves only through your tailnet")


def test_magicdns_https_certificates_and_where_the_tailnet_port_goes_are_each_checked_with_their_fix() -> None:
    good = checked(facts())
    assert good["magicdns"]["status"] == good["https"]["status"] == good["published"]["status"] == "passed"
    assert good["published"]["detail"] == (
        f"https://{HOST}:8445/ goes to the listener (127.0.0.1:7721), on your tailnet only"
    )
    bad = checked(facts(status=status(phone(), magic=False, certs=False), serve={}))
    assert (bad["magicdns"]["status"], bad["magicdns"]["detail"]) == (
        "failed", f"off in your tailnet: a phone cannot find {HOST} by its name"
    )  # fmt: skip
    assert "https://login.tailscale.com/admin/dns" in bad["magicdns"]["fix"]
    assert bad["https"]["status"] == "failed"
    assert bad["https"]["fix"].startswith("turn HTTPS Certificates on in Tailscale's admin console")
    assert (bad["published"]["status"], bad["published"]["detail"]) == (
        "failed", "Tailscale publishes nothing on port 8445"
    )  # fmt: skip
    assert bad["published"]["fix"].startswith(
        "turn remote access off and on again: x twice on the console's Phone page"
    )
    elsewhere = checked(facts(serve=served(local=9999)))["published"]
    assert elsewhere["detail"] == "port 8445 goes to http://127.0.0.1:9999, not to the listener (127.0.0.1:7721)"
    funneled = checked(facts(serve=served(funnel=(8445,))))["published"]
    assert (funneled["status"], funneled["detail"]) == (
        "failed", "Funnel is on for port 8445: the phone page would face the internet"
    )  # fmt: skip


def test_this_pc_opening_its_own_published_address_says_whether_and_how_it_answered() -> None:
    assert checked(facts())["self"] == {
        "id": "self", "title": "This PC reaches it", "status": "passed",
        "detail": f"https://{HOST}:8445/ answered in 240 ms", "fix": "",
    }  # fmt: skip
    silent = checked(facts(reached=Reached(None, 5000.0, "no answer within 5 s")))["self"]
    assert (silent["status"], silent["detail"]) == (
        "failed",
        f"https://{HOST}:8445/ did not answer: no answer within 5 s",
    )
    assert silent["fix"].startswith("if this PC cannot open it, no phone can")
    refused = checked(facts(reached=Reached(403, 30.0, "this page answers only to this computer's own Tailscale user")))
    assert refused["self"]["detail"] == (
        f"https://{HOST}:8445/ answered 403: this page answers only to this computer's own Tailscale user"
    )


def test_the_checks_come_in_the_order_the_owner_reads_them_the_phones_first() -> None:
    assert list(checked(facts())) == [
        "phone:my-iphone", "heard", "funnel", "tailscale", "listener", "published", "magicdns", "https", "self",
    ]  # fmt: skip
    tailscale = checked(facts())["tailscale"]
    assert (tailscale["status"], tailscale["detail"]) == ("passed", f"signed in as {OWNER}; this PC is {HOST} ({PC})")
    listener = checked(facts())["listener"]
    assert (listener["status"], listener["detail"]) == ("passed", "listens on this PC (127.0.0.1:7721)")


def test_tailscale_not_answering_on_this_pc_is_said_and_the_checks_that_need_it_are_left_out() -> None:
    missing = "Tailscale is not installed (https://tailscale.com/download)"
    found = checked(facts(status={}, problem=missing, serve={}, reached=None))
    assert list(found) == ["heard", "tailscale", "listener"]
    assert (found["tailscale"]["status"], found["tailscale"]["detail"]) == ("failed", missing)
    assert found["tailscale"]["fix"] == "install Tailscale (https://tailscale.com/download) and sign in"
    stopped = checked(facts(status={"BackendState": "Stopped"}))["tailscale"]
    assert (stopped["status"], stopped["detail"]) == ("failed", "Tailscale is Stopped on this PC")
    assert stopped["fix"] == "open Tailscale on this PC and sign in (or run `tailscale up`)"
    down = (
        "failed",
        "Clank's service does not run: nothing listens for the phone",
        "start it: `clank serve --background`",
    )
    listener = checked(facts(listener=down))["listener"]
    assert (listener["status"], listener["detail"], listener["fix"]) == down
