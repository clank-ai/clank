"""What every client of the cloud provider's routes does the same way (design 0016 §14, §16): writing a cloud preset for
a model, or taking the one already written for it, so a second pass through Add a model (after a failed test, a
refused limit, a closed terminal) goes on from where the first left off instead of stopping at `exists`. The console's
Add a model and `clank model add` both use it; it draws nothing and reads nothing of a client's.
"""

from typing import Any

from clank.client import ClientError


def written(client: Any, body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """The preset written from a model (`POST /runtime/endpoints/openrouter/presets`), and False; or, when one is
    written for that model already (409 `exists`), that one, and True."""
    try:
        preset: dict[str, Any] = client.post("runtime/endpoints/openrouter/presets", body)
    except ClientError as error:
        if error.code != "exists":
            raise
        found = [each for each in client.get("runtime/presets") if each.get("model") == body["model"]]
        if not found:
            raise
        return dict(found[0]), True
    return preset, False
