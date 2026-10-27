"""Test support: the gateway as a workspace's container reaches it, through the edge (`edge:<port>`, the host its
clients write), each workspace named by a made-up key in the routes, as the service gives them its key's SHA-256 (design
0016 §9), and the headers Clank's MCP server in that container sends."""

import hashlib

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes

EDGE = f"http://edge:{GatewaySettings().port}"  # where a workspace's container reaches the gateway
HERE = f"http://127.0.0.1:{GatewaySettings().port}"  # where the service and VS Code reach it


def made_up_key(workspace: str) -> str:
    """A workspace's key at the gateway, made up for a test."""
    return f"clank-ws-made-up-{workspace}-key"


def keyed(*workspaces: str) -> Routes:
    """Routes that name each workspace by its made-up key, each kept on this machine."""
    routes = Routes()
    bounds = {
        hashlib.sha256(made_up_key(name).encode()).hexdigest(): {
            "workspace": name, "models": "this-machine", "answered": False, "question": None,
        }
        for name in workspaces
    }  # fmt: skip
    routes.update({"slots": {}, "roles": {}, "workspaces": bounds})
    return routes


def agent_headers(workspace: str) -> dict[str, str]:
    """The headers of a call by Clank's MCP server in the workspace's container: its workspace's key."""
    return {"Authorization": f"Bearer {made_up_key(workspace)}"}
