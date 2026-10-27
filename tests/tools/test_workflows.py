"""Design 0014 §2: Docker Engine's first recording is made by a job of the repository's CI that runs only by hand, on
GitHub's ubuntu-24.04 runner. It records the engine running (with the tool's example containers), stopped (both of
Docker's units stopped first, so the tool's commands wake nothing, and started again after, whatever happened) and as
a user the job makes outside the docker group, then merges the three and prints the recording in its log between two
marker lines, with `docker version` on record. It adds no action: only the checkout the checks already use. The
workflow is read as text, since Clank has no YAML library (design 0014 §7)."""

import json
import re
from pathlib import Path

import pytest

from tools import capture_docker_engine as capture_tool

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def steps(text: str) -> list[str]:
    """Each step of the workflow's one job, as its text."""
    return [f"- {part}" for part in re.split(r"\n\s+- (?=name:|uses:)", text.split("steps:", 1)[1])[1:]]


def test_the_recording_job_runs_only_by_hand_and_prints_the_recording_between_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (WORKFLOWS / "record-docker-engine.yml").read_text(encoding="utf-8")
    triggers = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert [line.strip() for line in triggers.splitlines()] == ["workflow_dispatch:"], "by hand, and only by hand"
    assert "runs-on: ubuntu-24.04\n" in text
    assert "permissions:\n  contents: read\n" in text
    checkout = re.search(r"uses: (actions/checkout@\w+)", (WORKFLOWS / "checks.yml").read_text(encoding="utf-8"))
    assert checkout is not None
    assert re.findall(r"uses: (\S+)", text) == [checkout.group(1)], "no action but the checkout the checks use"
    found = steps(text)
    said = "\n".join(found)
    assert "docker version" in said
    tool = "capture_docker_engine.py"
    running = next(step for step in found if "--state running" in step)
    assert "--examples" in running
    stopped = next(step for step in found if "--state stopped" in step)
    assert stopped.index("sudo systemctl stop docker.socket docker.service") < stopped.index(tool)
    again = found[found.index(stopped) + 1]
    assert "if: always()" in again
    assert "sudo systemctl start docker.socket docker.service" in again
    denied = next(step for step in found if '--state "no access"' in step)
    user = re.search(r"sudo useradd [^\n]*?(\S+)\n", denied)
    assert user is not None
    assert f"sudo -u {user.group(1)} python3" in denied
    assert "docker" not in denied.split("useradd", 1)[1].split("\n", 1)[0], "made outside the docker group"
    assert "--merge" in found[-1]
    assert "sudo python3" not in text, "the tool itself never runs as root"
    for state in capture_tool.STATES:
        (tmp_path / f"{state}.json").write_text(json.dumps(sample(state)), encoding="utf-8")
    out = tmp_path / "program.json"
    files = [str(tmp_path / f"{state}.json") for state in capture_tool.STATES]
    assert capture_tool.main(["--merge", *files, "--where", "a test", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert printed.count(capture_tool.BEGINS) == printed.count(capture_tool.ENDS) == 1
    between = printed.split(capture_tool.BEGINS + "\n", 1)[1].split(capture_tool.ENDS, 1)[0]
    assert json.loads(between) == json.loads(out.read_text(encoding="utf-8"))


def sample(state: str) -> dict[str, object]:
    """A capture of one state, as the tool writes it, its engine in that state."""
    systemd = " ".join(capture_tool.SYSTEMD)
    version = " ".join(["docker", "-H", capture_tool.SOCKET, "version", "--format", capture_tool.VERSION])
    active = [0, "LoadState=loaded\nActiveState=active\n", 0.01, ""]
    answers = {
        "running": {systemd: active, version: [0, "28.0.4\n", 0.05, ""]},
        "stopped": {systemd: [0, "LoadState=loaded\nActiveState=inactive\n", 0.01, ""]},
        "no access": {systemd: active, version: [1, "\n", 0.02, "permission denied while trying to connect\n"]},
    }
    found = "28.0.4" if state == "running" else ""
    return {"state": state, "version": found, "command": "/usr/bin/docker", "answers": answers[state], "replaced": []}
