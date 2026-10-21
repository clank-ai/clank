"""Design 0016 §11 and §13: the Monitor with a cloud model, in the service's words. The heading line says what the
followed session cost so far (its subagents' with it); the Context window's "On the GPU exactly" says it does not apply
(the model runs at OpenRouter's provider); the Flow view says the flow's cost so far in its heading and in Models in
this flow, and each box's cost when it is chosen."""

from datetime import UTC
from typing import Any

from clank.components.agents.console import contextgpu, flowpanels
from clank.components.agents.console.contextpanel import gpu_line
from clank.components.agents.console.flowview import heading as flow_heading
from clank.components.agents.console.following import Seen
from clank.components.agents.console.monitor import heading
from clank.components.agents.context import CLOUD_GPU

COST = {"usd": 1.84, "requests": 310, "estimated_usd": 0.0, "said": "$1.84 · 310 requests",
        "boxes": {"b1": {"usd": 0.92, "requests": 140, "said": "$0.92 · 140 requests"}}}  # fmt: skip
VIEW: dict[str, Any] = {
    "flow": "paper/review", "title": "Review the paper", "workspace": "paper", "run": None, "cost": COST,
    "boxes": [{"id": "b1", "type": "work", "state": "done", "title": "Read the draft",
               "preset": "cloud-example-coder"}],
    "models": [{"preset": "cloud-example-coder", "title": "cloud: Example Coder", "boxes": 1, "loaded": True}],
}  # fmt: skip


def test_the_heading_says_what_the_followed_session_cost_so_far() -> None:
    head = {"session": "ses_1", "title": "Fix the tests", "agent": "build", "status": "busy", "steps": 3, "calls": 5,
            "cost": {"said": "$0.84 · 142 requests"}}  # fmt: skip
    said = heading("session", Seen(workspace="paper", head=head), UTC).plain
    assert "this session $0.84 · 142 requests" in said


def test_on_the_gpu_exactly_does_not_apply_to_a_cloud_model() -> None:
    totals = {"gpu": {"device": "cloud", "said": CLOUD_GPU}, "holder": {}, "facts": {"engine": {"on_gpu": False}}}
    line = gpu_line(totals)
    assert line is not None
    assert line.plain == f"On the GPU exactly: {CLOUD_GPU}"
    assert [each.plain for each in contextgpu.gpu(totals, None, UTC)] == [line.plain]
    assert CLOUD_GPU == "does not apply: the model runs at its cloud provider, not on this machine"


def test_the_flow_view_says_the_flows_cost_and_each_boxs() -> None:
    assert "cost so far $1.84 · 310 requests" in flow_heading(VIEW, UTC).plain
    lines = [line.plain for line in flowpanels.models(VIEW, 100)]
    assert "this flow so far: $1.84 · 310 requests" in lines
    chosen = " ".join(line.plain for line in flowpanels.selected(VIEW, "b1", 100, UTC))
    assert "$0.92 · 140 requests" in chosen
