"""What a workspace's cloud bound says (design 0016 §9; decisions 0103 and 0112), for every client: its bound in a line,
and what changing it does, said before it is changed (the question asked once is `cloud.py`'s). The service answers its
views in these words; the console, the commands, VS Code and the phone's app to come show them as they are and never
decide a workspace's consent themselves.

Allowing a workspace the cloud names first each of your MCP servers with secrets its agent gets (decision 0168): its
agent can read their values, and with the cloud model a model at a provider will be able to read them too.

It is the service's: it reads no client's state.
"""


def bound_said(name: str, models: str, answered: str) -> str:
    """The workspace's bound in a line."""
    if models == "cloud":
        return f"may use the cloud model: {name}'s requests may go to OpenRouter"
    if answered:
        return f"kept on this machine: {name} never uses the cloud model"
    return f"not asked yet: {name} is asked once before its agent uses the cloud model"


def carried_said(name: str, carried: dict[str, list[str]]) -> str:
    """What allowing the workspace the cloud means for your MCP servers with secrets its agent gets (each with the names
    of its values, decision 0168); empty when it gets none."""
    if not carried:
        return ""
    each = [f"{server} ({', '.join(names)})" for server, names in sorted(carried.items())]
    listed = each[0] if len(each) == 1 else f"{', '.join(each[:-1])} and {each[-1]}"
    servers = "server" if len(each) == 1 else "servers"
    return (
        f"{name}'s agent gets your MCP {servers} with secrets {listed}, and can read their values: with the cloud "
        "model, a model at a provider will be able to read them too. To keep a server's values here, take it away "
        "first (m on the folder's page, or `clank mcp hold NAME` in the folder)."
    )


def confirm_said(name: str, carried: dict[str, list[str]] | None = None) -> dict[str, str]:
    """What changing the workspace's bound does, said before it is changed: allowing it (naming your MCP servers with
    secrets its agent gets, `carried`), or keeping it here."""
    secrets = carried_said(name, carried or {})
    return {
        "allow": f"From its next request, {name}'s agent may send OpenRouter and the model's provider your messages, "
        "what it reads of the folder and command output; Notion pages and the MCP servers marked local never go. "
        + (f"{secrets} " if secrets else "")
        + "Its earlier sessions and its folder may hold research: a workspace made for the purpose is safer.",
        "local": f"From its next request, {name} never uses the cloud model: its requests to it are refused, and a "
        "local model serves it.",
    }
