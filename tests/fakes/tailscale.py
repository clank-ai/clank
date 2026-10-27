"""What Tailscale's command says, for tests (design 0025 §2: the phone's checkup reads it): `tailscale status --json`
with this PC, its user and its peers, and `tailscale serve status --json` publishing the phone's listener, in the
shapes Tailscale 1.102 writes them (the fields the checkup reads, with iOS's own habit of naming itself `localhost`).
"""

from typing import Any

OWNER = "owner@example.com"
OTHER = "other@example.com"
HOST = "desk.tail0.ts.net"
PC = "100.64.0.1"  # this PC's address on the tailnet
PHONE = "100.64.0.7"  # the phone's


def phone(**changes: Any) -> dict[str, Any]:
    """The owner's iPhone as a peer: offline, last seen at 17:00 UTC on 2026-10-26; `changes` replace its fields."""
    peer = {
        "HostName": "localhost",
        "DNSName": "my-iphone.tail0.ts.net.",
        "OS": "iOS",
        "Online": False,
        "LastSeen": "2026-10-26T17:00:00Z",
        "UserID": 1,
        "TailscaleIPs": [PHONE, "fd7a:115c:a1e0::7"],
        "KeyExpiry": "2027-04-01T00:00:00Z",
        "Expired": None,
    }
    return {**peer, **changes}


def status(*peers: dict[str, Any], magic: bool = True, certs: bool = True, state: str = "Running") -> dict[str, Any]:
    """`tailscale status --json`: this PC, signed in as the owner, with these peers; MagicDNS and HTTPS certificates
    on or off."""
    return {
        "BackendState": state,
        "Self": {
            "HostName": "DESK",
            "DNSName": f"{HOST}.",
            "OS": "windows",
            "Online": True,
            "UserID": 1,
            "TailscaleIPs": [PC, "fd7a:115c:a1e0::1"],
        },
        "User": {"1": {"ID": 1, "LoginName": OWNER}, "2": {"ID": 2, "LoginName": OTHER}},
        "CurrentTailnet": {"Name": OWNER, "MagicDNSSuffix": "tail0.ts.net", "MagicDNSEnabled": magic},
        "CertDomains": [HOST] if certs else None,
        "Peer": {f"nodekey:{index}": peer for index, peer in enumerate(peers)},
    }


def served(port: int = 8445, local: int = 7721, funnel: tuple[int, ...] = ()) -> dict[str, Any]:
    """`tailscale serve status --json`: the tailnet port sent to the listener on this PC; Funnel on for `funnel`."""
    found: dict[str, Any] = {
        "TCP": {str(port): {"HTTPS": True}},
        "Web": {f"{HOST}:{port}": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{local}"}}}},
    }
    if funnel:
        found["AllowFunnel"] = {f"{HOST}:{each}": True for each in funnel}
    return found
