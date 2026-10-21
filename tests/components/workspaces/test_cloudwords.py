"""Design 0016 §9 and §10, decisions 0103 and 0112: what a workspace's cloud bound says is the service's, for every
client (the owner's rule of 2026-10-21): its bound is one line, and what changing it does is said first."""

from clank.components.workspaces.cloudwords import bound_said, confirm_said


def test_the_bound_is_one_line() -> None:
    assert bound_said("paper", "cloud", "") == "may use the cloud model: paper's requests may go to OpenRouter"
    assert bound_said("paper", "this-machine", "2026-10-21T09:00:00.000Z").startswith("kept on this machine")
    assert bound_said("paper", "this-machine", "").startswith("not asked yet")


def test_changing_the_bound_says_what_changes_before_it_does() -> None:
    said = confirm_said("paper")
    assert said["allow"].startswith("From its next request, paper's agent may send OpenRouter")
    assert "Notion pages and the MCP servers marked local never go" in said["allow"]
    assert said["local"].startswith("From its next request, paper never uses the cloud model")
