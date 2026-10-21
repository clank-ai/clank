"""What a workspace's cloud bound says (design 0016 §9; decisions 0103 and 0112), for every client: its bound in a line,
and what changing it does, said before it is changed (the question asked once is `cloud.py`'s). The service answers its
views in these words; the console, the commands, VS Code and the phone's app to come show them as they are and never
decide a workspace's consent themselves.

It is the service's: it reads no client's state.
"""


def bound_said(name: str, models: str, answered: str) -> str:
    """The workspace's bound in a line."""
    if models == "cloud":
        return f"may use the cloud model: {name}'s requests may go to OpenRouter"
    if answered:
        return f"kept on this machine: {name} never uses the cloud model"
    return f"not asked yet: {name} is asked once before its agent uses the cloud model"


def confirm_said(name: str) -> dict[str, str]:
    """What changing the workspace's bound does, said before it is changed: allowing it, or keeping it here."""
    return {
        "allow": f"From its next request, {name}'s agent may send OpenRouter and the model's provider your messages, "
        "what it reads of the folder and command output; Notion pages and the MCP servers marked local never go. Its "
        "earlier sessions and its folder may hold research: a workspace made for the purpose is safer.",
        "local": f"From its next request, {name} never uses the cloud model: its requests to it are refused, and a "
        "local model serves it.",
    }
