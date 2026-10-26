"""Design 0004 §3 and §6, design 0002 §2.9: a workspace's container mounts its folder at /workspace and nothing else of
the machine (its home is a volume of its own), runs as the image's user with no capability and no new privileges, on an
internal network of its own only, within its CPU, memory and process limits, under Clank's labels; the edge is on the
network that reaches the host (each workspace's own it joins when that workspace opens), with a read-only root, small
limits, and a command that forwards the gateway's port and nothing else. A folder whose path has a comma or a quote
still mounts as itself. Design 0004 §10: a workspace's container tells numerical libraries how many CPUs it has.
Decision 0142 (design 0023 §7): Clank's programs are mounted read-only at /opt/clank in every container Clank runs,
not copied into the image, whose tag follows its Dockerfile alone."""

from pathlib import Path

import pytest

from clank.components.workspaces import sandbox
from clank.components.workspaces.sandbox import (
    edge_spec,
    image_folder,
    names,
    run_arguments,
    setup_spec,
    workspace_spec,
)

HOME = "abc123"
IMAGE = "clank-sandbox:0123456789ab"


def values(arguments: list[str], flag: str) -> list[str]:
    """Every value given after a flag."""
    return [arguments[index + 1] for index, part in enumerate(arguments) if part == flag]


def test_a_workspaces_container_mounts_its_folder_only_and_runs_within_its_limits() -> None:
    spec = workspace_spec(HOME, "my-project", r"C:\work\my-project", IMAGE, cpus=8.0, memory_mib=16384)
    arguments = run_arguments(spec)
    assert arguments[:2] == ["run", "--detach"]
    assert values(arguments, "--name") == ["clank-abc123-my-project"]
    assert values(arguments, "--mount") == [
        r"type=bind,source=C:\work\my-project,target=/workspace",
        f"type=bind,source={image_folder()},target=/opt/clank,readonly",
        "type=volume,source=clank-abc123-my-project-home,target=/home/agent",
    ], "its folder, Clank's programs read-only (decision 0142), its home"
    assert not {"-v", "--volume", "--privileged", "--cap-add", "--device", "-p", "--publish"} & set(arguments)
    assert values(arguments, "--network") == ["clank-abc123-my-project-net"]
    assert values(arguments, "--cap-drop") == ["ALL"]
    assert values(arguments, "--security-opt") == ["no-new-privileges"]
    assert values(arguments, "--user") == ["1000:1000"]
    assert values(arguments, "--workdir") == ["/workspace"]
    assert (values(arguments, "--cpus"), values(arguments, "--memory"), values(arguments, "--pids-limit")) == (
        ["8"],
        ["16384m"],
        ["1024"],
    )
    assert "--init" in arguments
    assert values(arguments, "--label") == [
        "clank.home=abc123",
        "clank.component=workspaces",
        "clank.record=my-project",
    ]
    assert arguments[-3:] == [IMAGE, "sleep", "infinity"]


def test_every_program_in_a_workspaces_container_starts_as_many_threads_as_the_container_has_cpus() -> None:
    # Docker's CPU limit does not change how many CPUs a program sees (a 16-CPU container saw 32, 2026-10-16), so the
    # container says it itself: a shell, a script or an MCP server started outside the agent is told too.
    spec = workspace_spec(HOME, "my-project", r"C:\work\my-project", IMAGE, cpus=16.0, memory_mib=16384)
    arguments = run_arguments(spec)
    assert values(arguments, "--env") == [
        "OMP_NUM_THREADS=16",
        "NUMBA_NUM_THREADS=16",
        "OPENBLAS_NUM_THREADS=16",
        "MKL_NUM_THREADS=16",
    ]
    assert arguments.index("--env") < arguments.index(IMAGE)
    small = workspace_spec(HOME, "small", r"C:\work\small", IMAGE, cpus=0.5, memory_mib=1024)
    assert "NUMBA_NUM_THREADS=1" in values(run_arguments(small), "--env"), "at least one"
    setup = setup_spec(HOME, "my-project", r"C:\work\my-project", IMAGE, cpus=8.0, memory_mib=4096, command="make")
    assert "NUMBA_NUM_THREADS=8" in values(run_arguments(setup), "--env")
    assert values(run_arguments(edge_spec(HOME, IMAGE, gateway_port=18210)), "--env") == []


def test_a_folder_whose_path_has_a_comma_or_a_quote_mounts_as_itself() -> None:
    spec = workspace_spec(HOME, "odd", r'C:\work\a,b "c"', IMAGE, cpus=2.0, memory_mib=4096)
    [folder, _programs, _home] = values(run_arguments(spec), "--mount")
    assert folder == r'type=bind,"source=C:\work\a,b ""c""",target=/workspace'


def test_the_edge_reaches_the_host_and_forwards_the_gateways_port_only() -> None:
    spec = edge_spec(HOME, IMAGE, gateway_port=18210)
    arguments = run_arguments(spec)
    assert values(arguments, "--name") == ["clank-abc123-edge"]
    assert values(arguments, "--network") == ["clank-abc123-outer"], "each workspace's network is joined as it opens"
    assert spec.networks == (("clank-abc123-outer", ""),)
    assert values(arguments, "--mount") == [f"type=bind,source={image_folder()},target=/opt/clank,readonly"]
    assert "--read-only" in arguments
    assert values(arguments, "--cap-drop") == ["ALL"]
    assert values(arguments, "--security-opt") == ["no-new-privileges"]
    assert values(arguments, "--add-host") == ["host.docker.internal:host-gateway"]
    assert values(arguments, "--label") == ["clank.home=abc123", "clank.component=workspaces", "clank.record=edge"]
    assert arguments[arguments.index(IMAGE) + 1 :] == [
        "python3", "/opt/clank/edge.py", "18210", "host.docker.internal", "18210"
    ]  # fmt: skip


def test_the_images_tag_follows_its_dockerfile_alone_since_the_programs_are_mounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 0142: a change to the bridge, an instruction or the edge's program rebuilds no image."""
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    (tmp_path / "bridge.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "boards.md").write_text("# Boards\n", encoding="utf-8")
    monkeypatch.setattr(sandbox, "image_folder", lambda: tmp_path)
    first = sandbox.image_tag()
    (tmp_path / "bridge.py").write_text("print(2)\n", encoding="utf-8")
    (tmp_path / "instructions" / "boards.md").write_text("# Boards, said again\n", encoding="utf-8")
    assert sandbox.image_tag() == first
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:24.04\nRUN true\n", encoding="utf-8")
    assert sandbox.image_tag() != first
    setup = setup_spec(HOME, "my-project", r"C:\work\my-project", IMAGE, cpus=8.0, memory_mib=4096, command="make")
    assert f"type=bind,source={tmp_path},target=/opt/clank,readonly" in values(run_arguments(setup), "--mount")


def test_the_names_of_one_homes_networks_volumes_and_containers() -> None:
    found = names(HOME)
    assert (found.inner("my-project"), found.outer, found.edge) == (
        "clank-abc123-my-project-net",
        "clank-abc123-outer",
        "clank-abc123-edge",
    )
    assert (found.container("my-project"), found.volume("my-project")) == (
        "clank-abc123-my-project",
        "clank-abc123-my-project-home",
    )
