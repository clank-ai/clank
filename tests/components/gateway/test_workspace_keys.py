"""Design 0016 §9 (decision 0075's keys, built for the cloud): each workspace has a key of its own at the gateway, made
once by the gateway's service and kept with the secrets (`workspace/<name>/gateway-key`), its SHA-256 kept with the
workspace's bound in the gateway's own state; the routes the gateway follows carry each key's hash with its workspace,
its bound, whether it was answered and its open question, never the key; a bound changed is in the next routes. Every
workspace has its key, the cloud in play or not: an agent's calls through the gateway to Notion, its flow and the
agents' part are refused without it."""

import hashlib
import json

from clank.components.gateway.service import Gateway
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig, add_openrouter

YOU = Actor(kind="user", via="console")


def test_every_workspace_has_its_own_key_the_cloud_in_play_or_not(rig: Rig) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    gateway.set_bound("notes", models="this-machine", answered=True)
    assert gateway.routes()["workspaces"] == {}, "no key until its agent is given one"
    assert gateway.bound("notes") == {
        "workspace": "notes",
        "models": "this-machine",
        "answered": True,
        "question": None,
    }
    key = gateway.workspace_key("notes", why="writing OpenCode's configuration")
    assert key.startswith("clank-ws-"), "no cloud provider agreed, and still its own key"
    assert (rig.kernel.home.secrets / "workspace" / "notes" / "gateway-key").read_text(encoding="utf-8") == key
    digest = hashlib.sha256(key.encode()).hexdigest()
    assert gateway.routes()["workspaces"] == {
        digest: {"workspace": "notes", "models": "this-machine", "answered": True, "question": None}
    }
    gateway.set_bound("notes", models="cloud")
    assert gateway.workspace_key("notes", why="writing OpenCode's configuration") == key, "allowing keeps it"


def test_a_workspaces_key_is_made_once_and_kept_with_the_secrets(rig: Rig) -> None:
    add_openrouter(rig, key=False)
    gateway: Gateway = rig.kernel.parts["gateway"]
    first = gateway.workspace_key("notes", why="writing OpenCode's configuration")
    again = gateway.workspace_key("notes", why="writing OpenCode's configuration")
    assert first == again
    assert len(first) >= 32
    assert (rig.kernel.home.secrets / "workspace" / "notes" / "gateway-key").read_text(encoding="utf-8") == first
    made = [
        event
        for event in rig.kernel.events.latest(50, types=["secret.set"])
        if event.data["scope"] == "workspace/notes"
    ]
    assert len(made) == 1, "made once"
    assert gateway.workspace_key("lab", why="a test") != first


def test_the_routes_carry_each_keys_hash_and_bound_never_the_key(rig: Rig) -> None:
    add_openrouter(rig, key=False)
    gateway: Gateway = rig.kernel.parts["gateway"]
    key = gateway.workspace_key("notes", why="a test")
    found = gateway.routes()
    digest = hashlib.sha256(key.encode()).hexdigest()
    assert found["workspaces"] == {
        digest: {"workspace": "notes", "models": "this-machine", "answered": False, "question": None}
    }
    assert key not in json.dumps(found)


def test_a_bound_changed_is_in_the_next_routes(rig: Rig) -> None:
    add_openrouter(rig, key=False)
    gateway: Gateway = rig.kernel.parts["gateway"]
    key = gateway.workspace_key("notes", why="a test")
    digest = hashlib.sha256(key.encode()).hexdigest()
    gateway.set_bound("notes", question="q-1a2b")
    assert gateway.routes()["workspaces"][digest]["question"] == "q-1a2b"
    gateway.set_bound("notes", models="cloud", answered=True, question=None)
    assert gateway.routes()["workspaces"][digest] == {
        "workspace": "notes", "models": "cloud", "answered": True, "question": None
    }  # fmt: skip
    gateway.set_bound("lab", models="this-machine", answered=True)
    assert gateway.bound("lab") == {"workspace": "lab", "models": "this-machine", "answered": True, "question": None}
    assert "lab" not in [each["workspace"] for each in gateway.routes()["workspaces"].values()], "no key yet"
    gateway.workspace_key("lab", why="writing OpenCode's configuration")
    lab = [each for each in gateway.routes()["workspaces"].values() if each["workspace"] == "lab"]
    assert lab == [{"workspace": "lab", "models": "this-machine", "answered": True, "question": None}]
